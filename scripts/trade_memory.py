#!/usr/bin/env python3
"""
trade_memory.py — Memory engine for the AI Trading Analyst plugin.

Vector store interface over Pinecone (serverless, integrated inference).

* Single source of truth for the record schema: ``scripts/trade_schemas.py``
* Shared scoring helpers (legacy parser): ``scripts/trade_scoring.py``

Slices 3a + 3b ship:
    init               Create the integrated-inference index (idempotent)
    ingest             Parse a TRADE-*.md report and upsert its chunks
                       (--archive flag delegates Drive upload to the calling skill)
    query              Semantic search over stored reports
    latest             Newest record's metadata as JSON
    list               Manifest listing across the namespace
    timeline           All records for a ticker, oldest→newest
    delete             GC for a ticker (--before YYYY-MM-DD optional)
    rebuild            Re-ingest every TRADE-*.md under a local directory
    recommend-tier     Tier the next sweep: prints `analyze` or `quick`
                       (Pinecone-unavailable: prints `analyze` and exits 0)
    doctor             Health check; exit codes 0 healthy / 1 degraded / 2 unavailable

Top-level ``--namespace NS`` overrides PINECONE_NAMESPACE for every subcommand.

Cloud-mode wiring (slice 7.5):
    When both PINECONE_PROXY_URL and PINECONE_PROXY_TOKEN are set, all
    read/write ops route via urllib through the Vercel proxy (the producer
    Pinecone key never enters the routine sandbox). See proxy/ for the
    deployment artifact. Admin ops (init / describe) remain local-only —
    the proxy intentionally doesn't expose them.

See ``plan/portfolio-routine-and-vector-memory.md`` §1 for the full spec.

Drive archive note (slice 3b architectural decision)
----------------------------------------------------
Python cannot invoke the Google_Drive MCP tools directly — those live in the
LLM/skill context. The ``ingest --archive`` flag therefore:

* If ``TRADE_DRIVE_ARCHIVE_FOLDER_ID`` is unset → emits a one-line setup hint
  on stderr (the upsert still proceeds; the archive is a no-op).
* If set → emits a structured ``[archive-todo] …`` line on stderr describing
  the search_files / create_file / create_file flow the calling skill must
  perform. The Pinecone upsert is authoritative either way.

The ``rebuild`` subcommand likewise handles local directories only. When given
a Drive folder ID (a token that doesn't look like a path), it errors out and
points the user at the equivalent skill-level flow.

Usage
-----

::

    export PINECONE_API_KEY=pcsk_...
    python3 scripts/trade_memory.py init
    python3 scripts/trade_memory.py ingest TRADE-ANALYSIS-AAPL.md
    python3 scripts/trade_memory.py query "bull case for apple" --ticker AAPL -n 5
    python3 scripts/trade_memory.py latest AAPL --type ANALYSIS
    python3 scripts/trade_memory.py recommend-tier AAPL
    python3 scripts/trade_memory.py doctor
"""

import argparse
import importlib.util
import json
import os
import pathlib
import re
import sys
from datetime import datetime, timedelta, timezone


# ---------------------------------------------------------------------------
# Sibling module resolution — works from any CWD or install location.
# Pattern documented in plan §"import resolution".
# ---------------------------------------------------------------------------

_HERE = pathlib.Path(__file__).resolve().parent


def _import_sibling(name: str):
    spec = importlib.util.spec_from_file_location(name, _HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


trade_schemas = _import_sibling("trade_schemas")
trade_scoring = _import_sibling("trade_scoring")


# ---------------------------------------------------------------------------
# Pinecone SDK — lazy-loaded so the rest of the script works (e.g. --help,
# legacy parser) without the SDK installed.
# ---------------------------------------------------------------------------


def _load_pinecone():
    try:
        from pinecone import Pinecone
        return Pinecone
    except ImportError:
        sys.exit(
            "Pinecone SDK not installed. Run: pip install 'pinecone>=5'\n"
            "(see requirements.txt)"
        )


class _ProxyHit:
    """Mimics the integrated-inference Pinecone Hit shape (``_score`` attr +
    ``fields`` dict) so ``cmd_query``'s rendering loop works unchanged in
    cloud mode.
    """

    def __init__(self, hit_dict):
        self._score = hit_dict.get("_score", 0.0)
        self._id = hit_dict.get("_id")
        self.fields = hit_dict.get("fields", {}) or {}

    def get(self, key, default=None):
        # Tolerates dict-style access (some SDK versions return dict-like hits)
        return getattr(self, key, default)


class _ProxyResult:
    """Mimics the ``response.result`` shape (carrying ``.hits``)."""

    def __init__(self, hits_list):
        self.hits = [_ProxyHit(h) for h in hits_list]


class _ProxyQueryResponse:
    """Mimics the integrated-inference ``SearchRecordsResponse`` shape so the
    same ``response.result.hits`` traversal works in both modes.
    """

    def __init__(self, hits_list):
        self.result = _ProxyResult(hits_list)


class _ProxyFetchResponse:
    """Mimics the ``Index.fetch`` response shape (``response.vectors`` is a
    dict of id → vector-with-.metadata).
    """

    class _Vector:
        def __init__(self, metadata):
            self.metadata = metadata

    def __init__(self, records_dict):
        self.vectors = {
            vid: self._Vector(meta) for vid, meta in records_dict.items()
        }


class ProxyHTTPError(Exception):
    """Raised when a cloud-mode HTTPS call to the proxy fails. Carries the
    HTTP status code, the parsed response body (or a ``{"raw": ...}`` fallback
    for non-JSON), and the URL that was called.

    Doctor's auth check expects HTTP 400 (a validation_failed response from
    the proxy means auth succeeded but the empty payload was rejected) — so
    it deliberately catches this and inspects ``.status_code``.
    """

    def __init__(self, status_code: int, body, url: str):
        super().__init__(f"proxy {url} returned {status_code}: {body}")
        self.status_code = status_code
        self.body = body
        self.url = url


# ---------------------------------------------------------------------------
# VectorStore — wraps Pinecone integrated-inference operations
# ---------------------------------------------------------------------------


class VectorStore:
    """Thin Pinecone wrapper. Local-only in slice 3a; cloud-proxy support
    (PINECONE_PROXY_URL / PINECONE_PROXY_TOKEN) is structurally plumbed but the
    proxy branch isn't implemented yet (slice 7.5 deliverable).
    """

    def __init__(self, namespace: str = None):
        # Config (env defaults documented in plan §1 config table)
        self.api_key = os.environ.get("PINECONE_API_KEY")
        self.index_name = os.environ.get("PINECONE_INDEX", "trade-reports")
        self.embed_model = os.environ.get(
            "PINECONE_EMBED_MODEL", "llama-text-embed-v2"
        )
        self.cloud = os.environ.get("PINECONE_CLOUD", "aws")
        self.region = os.environ.get("PINECONE_REGION", "us-east-1")
        self.namespace = (
            namespace
            or os.environ.get("PINECONE_NAMESPACE")
            or "trade"
        )
        # Cloud proxy plumbing (slice 7.5; detected but not yet usable)
        self.proxy_url = os.environ.get("PINECONE_PROXY_URL")
        self.proxy_token = os.environ.get("PINECONE_PROXY_TOKEN")
        self._proxy_mode = bool(self.proxy_url and self.proxy_token)

        # Lazy state
        self._client = None
        self._index = None

    def _require_local_creds(self):
        """Ensure we can talk to Pinecone directly. In proxy mode, this is
        called only for admin ops (init / describe) that the proxy
        intentionally doesn't expose — and surfaces a clear error pointing
        the operator at a local invocation.
        """
        if self._proxy_mode:
            sys.exit(
                "This operation is local-only (the proxy intentionally "
                "doesn't expose admin ops like init/describe). Unset "
                "PINECONE_PROXY_URL and run from a workstation with "
                "PINECONE_API_KEY set."
            )
        if not self.api_key:
            sys.exit(
                "PINECONE_API_KEY is not set. Copy .env.example to .env, "
                "fill in your Pinecone key, and `set -a; source .env; set +a` "
                "before running this command."
            )

    def _proxy_post(self, op: str, payload: dict, timeout: float = 15.0,
                    attempts: int = None, backoff: float = 0.5):
        """POST a JSON payload to ``<proxy_url>/<op>`` with bearer auth.

        Returns the parsed JSON response on 200. Raises ``ProxyHTTPError``
        on any other status with the status code + response body attached
        so callers can branch (e.g. doctor's auth check expects 400, not
        200).

        Transient failures are retried with exponential backoff up to
        ``attempts`` total tries (default 3; override via the
        ``TRADE_PROXY_MAX_ATTEMPTS`` env var, e.g. ``1`` to disable retries
        in tests). A failure is "transient" when it is:
          - a network error / timeout (surfaced as status 0), or
          - an HTTP 5xx (server-side).
        Deterministic statuses (400 validation, 401 auth, 403 forbidden, 404,
        405, 429 rate-limit) are NOT retried — they raise on the first attempt
        so doctor's 400-expecting auth check stays fast and real client/auth
        errors surface immediately instead of after N backoffs.

        On 403 specifically: the proxy app itself NEVER emits 403 (every path
        in proxy/app.py emits 401/429/400/404/405/500/200), so a 403 is always
        a *persistent* infrastructure denial that will NOT clear on retry —
        most often the Claude cloud-sandbox egress proxy
        (``x-deny-reason: host_not_allowed`` / body ``Host not in allowlist``:
        the proxy host is missing from the routine environment's Custom
        allowed-domains), or a Vercel edge/firewall rule. We fail fast and let
        ``doctor`` print the remediation rather than burning N backoffs.

        If ``VERCEL_PROTECTION_BYPASS`` is set (the user kept Vercel
        Deployment Protection on and generated a Protection Bypass for
        Automation token), the corresponding header is attached so the
        request reaches the function instead of the Vercel SSO gate.
        Both header AND query-param forms are accepted by Vercel; the
        header is cleaner — no need to fold into the URL.
        """
        import json as _json
        import urllib.request
        import urllib.error
        import socket
        import time
        if attempts is None:
            try:
                attempts = int(os.environ.get("TRADE_PROXY_MAX_ATTEMPTS", "3"))
            except ValueError:
                attempts = 3
        attempts = max(1, attempts)
        url = self.proxy_url.rstrip("/") + "/" + op
        body = _json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.proxy_token}",
            "Content-Type": "application/json",
            "User-Agent": "trade-memory.py/slice7.5",
        }
        bypass = os.environ.get("VERCEL_PROTECTION_BYPASS")
        if bypass:
            headers["x-vercel-protection-bypass"] = bypass
            # Vercel docs recommend also setting this so the bypass
            # cookie isn't set on the response (we don't want it stuck
            # to a long-lived client). "samesitenoneblob" is opaque to
            # callers and just instructs Vercel not to set the cookie.
            headers["x-vercel-set-bypass-cookie"] = "false"
        req = urllib.request.Request(
            url,
            data=body,
            headers=headers,
            method="POST",
        )

        def _retryable(status: int) -> bool:
            # 0 = network/timeout, 5xx = server — genuinely transient.
            # 403 is a PERSISTENT edge/egress allowlist denial (the app never
            # emits 403), so it must fail fast — retrying just wastes backoff.
            # Everything else (400/401/403/404/405/429) is deterministic.
            return status == 0 or status >= 500

        last_err = None
        for attempt in range(1, attempts + 1):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return _json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                # HTTPError is a URLError subclass — must be caught first.
                raw = e.read().decode("utf-8", errors="replace")
                try:
                    parsed = _json.loads(raw)
                except Exception:
                    parsed = {"raw": raw}
                last_err = ProxyHTTPError(e.code, parsed, url)
                if not _retryable(e.code) or attempt == attempts:
                    raise last_err
            except (urllib.error.URLError, socket.timeout) as e:
                # Connect errors/timeouts (URLError) and read timeouts
                # (socket.timeout, not a URLError subclass) — both transient.
                last_err = ProxyHTTPError(
                    0, {"error": "network", "reason": str(e)}, url
                )
                if attempt == attempts:
                    raise last_err
            # Transient failure with attempts remaining: back off and retry.
            delay = backoff * (2 ** (attempt - 1))
            sys.stderr.write(
                f"[proxy-retry] {op} attempt {attempt}/{attempts} failed "
                f"(status {last_err.status_code}); retrying in {delay:.1f}s\n"
            )
            time.sleep(delay)
        # Defensive: the loop always returns or raises above. Re-raise the
        # last error rather than fall through to None on any unforeseen path.
        raise last_err

    @property
    def client(self):
        if self._client is None:
            self._require_local_creds()
            Pinecone = _load_pinecone()
            self._client = Pinecone(api_key=self.api_key)
        return self._client

    @property
    def index(self):
        if self._index is None:
            self._index = self.client.Index(self.index_name)
        return self._index

    # -----------------------------------------------------------------------
    # Index lifecycle
    # -----------------------------------------------------------------------

    def index_exists(self) -> bool:
        try:
            return any(
                i.name == self.index_name for i in self.client.list_indexes()
            )
        except Exception:
            return False

    def create_index(self) -> bool:
        """Idempotent: returns True if a new index was created, False if it
        already existed.
        """
        if self.index_exists():
            return False
        # Integrated-inference index: Pinecone hosts the embedding model. The
        # field_map tells Pinecone which field in each record holds the text
        # to embed — we use `"text"` per the §1 record-schema convention.
        self.client.create_index_for_model(
            name=self.index_name,
            cloud=self.cloud,
            region=self.region,
            embed={
                "model": self.embed_model,
                "field_map": {"text": "text"},
            },
        )
        return True

    # -----------------------------------------------------------------------
    # Upsert / query
    # -----------------------------------------------------------------------

    def upsert_records(self, records):
        """Upsert RecordMetadata instances via integrated inference.

        Local mode: calls ``Index.upsert_records(namespace, records)``
        directly. Cloud mode: POSTs to ``<proxy>/upsert`` with the records
        list; the proxy re-validates against the same trade_schemas before
        forwarding to Pinecone.
        """
        # Defense in depth: re-validate that every record is a real
        # RecordMetadata instance (callers shouldn't pass raw dicts).
        for r in records:
            if not isinstance(r, trade_schemas.RecordMetadata):
                raise TypeError(
                    f"upsert_records expects RecordMetadata instances; "
                    f"got {type(r).__name__}. Build via "
                    "trade_schemas.RecordMetadata(...) so validation fires."
                )
        if not trade_schemas.is_allowed_namespace(self.namespace):
            raise ValueError(
                f"Namespace {self.namespace!r} not in allowlist "
                f"{sorted(trade_schemas.ALLOWED_NAMESPACES)}. "
                "Extend trade_schemas.ALLOWED_NAMESPACES if intentional."
            )
        if self._proxy_mode:
            # Send pre-lift dicts (id, list-form catalysts) so the proxy
            # can re-validate against RecordMetadata cleanly. The proxy
            # then calls .to_pinecone_record() to produce the on-wire
            # shape — single source of truth lives in trade_schemas.py.
            payload = [r.model_dump(exclude_none=True) for r in records]
            return self._proxy_post("upsert", {
                "namespace": self.namespace,
                "records": payload,
            })
        payload = [r.to_pinecone_record() for r in records]
        return self.index.upsert_records(self.namespace, payload)

    def query(self, text: str, top_k: int = 5, filter_dict: dict = None):
        """Integrated-inference semantic search.

        Local mode returns the raw ``SearchRecordsResponse``; cloud mode
        returns a ``_ProxyQueryResponse`` wrapper exposing the same
        ``response.result.hits[*]._score / .fields`` shape callers consume
        in ``cmd_query``.
        """
        if self._proxy_mode:
            resp = self._proxy_post("query", {
                "namespace": self.namespace,
                "text": text,
                "top_k": top_k,
                **({"filter": filter_dict} if filter_dict else {}),
            })
            return _ProxyQueryResponse(resp.get("hits", []))
        q = {"inputs": {"text": text}, "top_k": top_k}
        if filter_dict:
            q["filter"] = filter_dict
        return self.index.search(namespace=self.namespace, query=q)

    # -----------------------------------------------------------------------
    # Read helpers (slice 3b — latest / list / timeline / delete / doctor)
    # -----------------------------------------------------------------------

    def list_ids(self, prefix: str = None):
        """Yield every record ID in the current namespace (optionally filtered
        by prefix). Walks pagination explicitly so we don't rely on SDK
        generator behavior — the routine plan calls for deterministic
        pagination. Cloud mode POSTs to /list and reuses the same
        prefix+pagination_token contract.

        Note: the proxy REQUIRES ``prefix`` (lexical-scope guard). When the
        caller doesn't supply one in cloud mode, we synthesize the empty
        string ``""`` which Pinecone treats as "any prefix" — equivalent to
        no filter, just made explicit for the proxy's payload validation.
        """
        page_limit = 100
        token = None
        # Proxy requires a non-empty prefix; "" wouldn't pass min_length=1.
        # In cloud mode without a prefix, list every uppercase letter +
        # digit + dot/hyphen separately. That's 38 paginated streams worst
        # case (A-Z + 0-9 + . + -), still cheap (< 200ms total at typical
        # index sizes). Most real callers always pass a prefix anyway.
        if self._proxy_mode and not prefix:
            seeds = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-")
            for seed in seeds:
                yield from self.list_ids(prefix=seed)
            return

        while True:
            if self._proxy_mode:
                payload = {
                    "namespace": self.namespace,
                    "prefix": prefix,
                    "limit": page_limit,
                }
                if token:
                    payload["pagination_token"] = token
                resp = self._proxy_post("list", payload)
                for vid in resp.get("ids", []):
                    yield vid
                token = resp.get("next_pagination_token")
            else:
                kwargs = {"namespace": self.namespace, "limit": page_limit}
                if prefix:
                    kwargs["prefix"] = prefix
                if token:
                    kwargs["pagination_token"] = token
                resp = self.index.list_paginated(**kwargs)
                vectors = getattr(resp, "vectors", None) or []
                for v in vectors:
                    vid = v.get("id") if hasattr(v, "get") else getattr(v, "id", None)
                    if vid:
                        yield vid
                pagination = getattr(resp, "pagination", None)
                token = pagination.get("next") if pagination and hasattr(pagination, "get") else (
                    getattr(pagination, "next", None) if pagination else None
                )
            if not token:
                break

    def fetch_meta(self, ids):
        """Fetch metadata for a batch of IDs. Returns ``{id: {meta_dict}}``.
        Pinecone caps a single fetch around ~1000 IDs; we batch in 100s to
        match the list page size and the proxy's per-call ceiling.
        """
        ids = list(ids)
        if not ids:
            return {}
        result = {}
        for start in range(0, len(ids), 100):
            chunk = ids[start : start + 100]
            if self._proxy_mode:
                resp = self._proxy_post("fetch", {
                    "namespace": self.namespace,
                    "ids": chunk,
                })
                # /fetch returns {"records": {id: metadata_dict}}
                for vid, meta in (resp.get("records") or {}).items():
                    result[vid] = dict(meta) if meta else {}
            else:
                resp = self.index.fetch(ids=chunk, namespace=self.namespace)
                vectors = getattr(resp, "vectors", None) or {}
                for vid, vec in vectors.items():
                    meta = getattr(vec, "metadata", None)
                    if meta is None and hasattr(vec, "get"):
                        meta = vec.get("metadata", {})
                    result[vid] = dict(meta) if meta else {}
        return result

    def delete_ids(self, ids):
        """Delete records by ID. No-op on empty input. Cloud mode POSTs to
        /delete with ``confirm: "yes"`` (the proxy rejects deletes without
        the explicit confirm field — no accidental bulk wipes via leaked
        bearer).
        """
        ids = list(ids)
        if not ids:
            return 0
        for start in range(0, len(ids), 100):
            chunk = ids[start : start + 100]
            if self._proxy_mode:
                self._proxy_post("delete", {
                    "namespace": self.namespace,
                    "ids": chunk,
                    "confirm": "yes",
                })
            else:
                self.index.delete(ids=chunk, namespace=self.namespace)
        return len(ids)

    def describe_index(self):
        """Return the IndexModel — used by `doctor` to verify embedding-model
        drift. Cached on the client; cheap to call.
        """
        return self.client.describe_index(self.index_name)

    def describe_stats(self):
        """Return ``Index.describe_index_stats()`` raw. `doctor` and `delete`
        consume the per-namespace vector_count from ``stats.namespaces``.
        """
        return self.index.describe_index_stats()


# ---------------------------------------------------------------------------
# ID helpers — record IDs are part of the public contract; their lexical
# sortability is what makes `latest` / `timeline` cheap.
# ---------------------------------------------------------------------------

# Mirror of trade_schemas.RECORD_ID_PATTERN; split here so we can introspect
# the fields without re-parsing the regex on every record.
def _parse_id(rid: str):
    """Return ``(ticker, type, timestamp, section, chunk_index)`` or None
    if the ID doesn't match the contract grammar.
    """
    parts = rid.split(":")
    if len(parts) != 5:
        return None
    try:
        chunk_idx = int(parts[4])
    except ValueError:
        return None
    return (parts[0], parts[1], parts[2], parts[3], chunk_idx)


def _newest_timestamp(ids):
    """Return the lexically-largest ``YYYYMMDD-HHMM`` timestamp across IDs,
    or None if the iterable is empty / unparseable.
    """
    best = None
    for rid in ids:
        parsed = _parse_id(rid)
        if parsed is None:
            continue
        ts = parsed[2]
        if best is None or ts > best:
            best = ts
    return best


def _meta_display(meta: dict, drop_text: bool = True) -> dict:
    """Trim a metadata dict to the fields useful in CLI output. We hide the
    chunk text by default (verbose; `query` is the path that surfaces it).
    """
    out = dict(meta)
    if drop_text and "text" in out:
        del out["text"]
    return out


def _display_date(meta: dict) -> str:
    """Pull a display date out of a metadata dict. Prefers ``generated_date``
    (the canonical field per the §1 contract); falls back to ``generated_at[:10]``
    for legacy records ingested before the parse_report derivation landed
    (slice 3a fixtures). Returns ``"-"`` if neither is set.
    """
    d = meta.get("generated_date")
    if d:
        return str(d)
    g = meta.get("generated_at")
    if g:
        return str(g)[:10]
    return "-"


# ---------------------------------------------------------------------------
# Report parsing — frontmatter first, legacy fallback, filename-only floor
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_FILENAME_RE = re.compile(
    r"^TRADE-([A-Z]+)-([A-Z0-9.\-]+?)(?:-\d{8}-\d{4})?\.md$"
)


def parse_report(file_path: str):
    """Parse a TRADE-*.md file into a list of validated ``RecordMetadata``
    instances — one per chunk.

    Ingest precedence (per plan §2):
        1. YAML frontmatter (preferred)
        2. Legacy body parser
        3. Filename-only floor
    """
    path = pathlib.Path(file_path)
    text = path.read_text(encoding="utf-8")

    fm_match = _FRONTMATTER_RE.match(text)
    if fm_match:
        meta_dict = _parse_yaml_frontmatter(fm_match.group(1))
        body = fm_match.group(2)
    else:
        meta_dict = _parse_legacy(path, text)
        body = text

    chunks = _chunk_by_section(body)
    if not chunks:
        # Empty body — at least produce one chunk so the record is upsertable.
        chunks = [("body", body or "(empty)")]

    # Derive generated_date from generated_at if the upstream skill omitted
    # it. The §1 contract table marks generated_date "always present", so we
    # backfill rather than ship records with a null value that recommend-tier
    # would then mishandle. (Slice 3a missed this; surfaced when implementing
    # the 30-day age rule for recommend-tier.)
    if meta_dict.get("generated_at") and not meta_dict.get("generated_date"):
        meta_dict["generated_date"] = str(meta_dict["generated_at"])[:10]

    records = []
    for i, (section, chunk_text) in enumerate(chunks):
        meta = dict(meta_dict)
        meta["section"] = section
        meta["chunk_index"] = i
        meta["source_path"] = path.name
        meta["text"] = chunk_text
        # schema_version always set explicitly (defaults to current version
        # but the explicit form catches stale fixtures with mismatched values)
        meta.setdefault("schema_version", trade_schemas.SCHEMA_VERSION)
        records.append(trade_schemas.RecordMetadata(**meta))
    return records


def _parse_yaml_frontmatter(yaml_text: str) -> dict:
    """Minimal YAML parser for our flat-key frontmatter subset.

    Intentionally hand-rolled to avoid pulling in PyYAML. The frontmatter shape
    is restricted to: ``key: value`` lines (scalars, strings, bools, ints,
    floats) plus the ``catalysts`` list (one-line ``[a, b, c]`` form).
    """
    result = {}
    for raw in yaml_text.split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip()
        val = val.strip()
        # Skip the marker line that just says we're a trade report
        if key == "trade_report":
            continue
        # Strip surrounding quotes
        if (val.startswith('"') and val.endswith('"')) or (
            val.startswith("'") and val.endswith("'")
        ):
            val = val[1:-1]
        # Type coercion
        if val.lower() == "true":
            result[key] = True
        elif val.lower() == "false":
            result[key] = False
        elif val.lower() in ("null", "none", "~", ""):
            result[key] = None
        elif val.startswith("[") and val.endswith("]"):
            inner = val[1:-1]
            items = [
                s.strip().strip('"').strip("'")
                for s in inner.split(",")
                if s.strip()
            ]
            result[key] = items
        else:
            # Try int → float → leave as string
            try:
                result[key] = int(val)
            except ValueError:
                try:
                    result[key] = float(val)
                except ValueError:
                    result[key] = val
    return result


def _parse_legacy(path: pathlib.Path, text: str) -> dict:
    """Fallback for frontmatter-less reports.

    Keys off filename for ticker + report_type, mtime for date, and a simple
    body regex for composite score. signal/grade are derived from the score
    via ``trade_scoring`` (consistent with what new frontmatter would set).
    """
    meta = {}
    m = _FILENAME_RE.match(path.name)
    if m:
        meta["report_type"] = m.group(1)
        meta["ticker"] = m.group(2)
    else:
        # Filename-only floor: still need *something* upsertable, so fall back
        # to UNKNOWN tickers. The plan's robustness section calls this out:
        # ingest never refuses a frontmatter-less report; it just warns.
        sys.stderr.write(
            f"[warn] {path.name}: filename doesn't match TRADE-<TYPE>-<TICKER>.md; "
            "using UNKNOWN placeholders\n"
        )
        meta["report_type"] = "ANALYSIS"  # safest default for the type enum
        meta["ticker"] = "UNKNOWN"

    # Date from mtime — better than wall-clock because re-ingest is stable
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    meta["generated_at"] = mtime.isoformat()
    meta["generated_date"] = meta["generated_at"][:10]

    # Composite score: look for "Composite Score: NN" or "Trade Score: NN/100"
    score_match = re.search(
        r"(?:Composite|Trade)\s+Score:?\s*(\d{1,3})", text, re.IGNORECASE
    )
    if score_match:
        score = int(score_match.group(1))
        score = max(0, min(100, score))
        meta["composite_score"] = score
        meta["signal"] = trade_scoring.trade_signal(score)
        meta["grade"] = trade_scoring.score_grade(score)

    return meta


def _chunk_by_section(body: str, max_chars: int = 1500, overlap: int = 100):
    """Split markdown body into (section_slug, chunk_text) tuples.

    Splits on ``## `` headers; long sections fall back to fixed-width
    windows with overlap so we stay under Pinecone's 40 KB metadata limit.
    """
    sections = re.split(r"\n(?=## )", body)
    result = []
    for section in sections:
        section = section.rstrip()
        if not section.strip():
            continue
        title_match = re.match(r"## (.*?)(?:\n|$)", section)
        title = title_match.group(1).strip() if title_match else "preamble"
        # Slug: lowercase, runs-of-non-alnum → "-", trim
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "section"
        if len(section) <= max_chars:
            result.append((slug, section))
        else:
            step = max(1, max_chars - overlap)
            for start in range(0, len(section), step):
                result.append((slug, section[start : start + max_chars]))
    return result


# ---------------------------------------------------------------------------
# CLI subcommands
# ---------------------------------------------------------------------------


def cmd_init(args):
    store = VectorStore(namespace=args.namespace)
    created = store.create_index()
    if created:
        print(
            f"Created index '{store.index_name}' "
            f"in {store.cloud}/{store.region} "
            f"with embedding model '{store.embed_model}'."
        )
    else:
        print(
            f"Index '{store.index_name}' already exists "
            "(idempotent no-op)."
        )
    return 0


def cmd_ingest(args):
    store = VectorStore(namespace=args.namespace)
    records = parse_report(args.file)
    if not records:
        print(f"[error] No chunks extracted from {args.file}", file=sys.stderr)
        return 1

    # Build IDs from the first record's identification fields. All chunks from
    # one report share ticker/type/timestamp; only the section + chunk_index
    # differ.
    first = records[0]
    ts = first.generated_at_compact()
    for rec in records:
        rec.id = (
            f"{rec.ticker}:{rec.report_type}:{ts}"
            f":{rec.section}:{rec.chunk_index}"
        )
        if args.run_id:
            rec.run_id = args.run_id

    store.upsert_records(records)
    print(
        f"Ingested {len(records)} chunk(s) from {pathlib.Path(args.file).name} "
        f"into Pinecone namespace '{store.namespace}'."
    )

    # --archive: Python can't invoke MCP tools directly, so we emit either a
    # setup hint (folder unset) or a structured todo for the calling skill to
    # act on (folder set). The Pinecone upsert above is the authoritative
    # outcome; archive failures are warnings, never errors.
    if args.archive:
        _handle_archive_flag(args.file, first.ticker)

    return 0


def _handle_archive_flag(file_path: str, ticker: str):
    """Emit the appropriate stderr message for `--archive`. See module
    docstring "Drive archive note" for the architectural rationale.
    """
    folder_id = os.environ.get("TRADE_DRIVE_ARCHIVE_FOLDER_ID")
    basename = pathlib.Path(file_path).name
    if not folder_id:
        sys.stderr.write(
            "[archive-setup] --archive requested but "
            "TRADE_DRIVE_ARCHIVE_FOLDER_ID is unset. To enable Drive "
            "mirroring: create a Drive folder via `/trade holdings` or "
            "directly in Drive, then `export "
            "TRADE_DRIVE_ARCHIVE_FOLDER_ID=<folder-id>`. "
            "Pinecone upsert succeeded; Drive upload skipped.\n"
        )
        return
    # Structured todo: the calling skill greps for "[archive-todo]" and runs
    # the three Drive MCP calls. Encoded as JSON on a single line so the
    # skill can parse it reliably without a custom format.
    todo = {
        "intent": "drive-archive",
        "file_path": str(pathlib.Path(file_path).resolve()),
        "file_basename": basename,
        "ticker": ticker,
        "archive_folder_id": folder_id,
        "flow": [
            "search_files(name=<TICKER>, parent=<archive_folder_id>, "
            "mimeType='application/vnd.google-apps.folder')",
            "if not found: create_file(name=<TICKER>, parent=<archive_folder_id>, "
            "mimeType='application/vnd.google-apps.folder') → ticker_folder_id",
            "create_file(name=<file_basename>, parent=<ticker_folder_id>, "
            "contents=<file>)",
        ],
    }
    sys.stderr.write("[archive-todo] " + json.dumps(todo) + "\n")


def cmd_query(args):
    store = VectorStore(namespace=args.namespace)
    filt = {}
    if args.ticker:
        filt["ticker"] = {"$eq": args.ticker}
    if args.type:
        filt["report_type"] = {"$eq": args.type}

    response = store.query(args.text, top_k=args.n, filter_dict=filt or None)
    # Pinecone SearchRecordsResponse: response.result.hits[*]
    # Each hit has: _id, _score, fields
    hits = []
    try:
        hits = response.result.hits
    except AttributeError:
        # Some SDK versions return dict-like
        hits = response.get("result", {}).get("hits", [])

    if not hits:
        print("No hits.")
        return 0

    for i, hit in enumerate(hits):
        # Normalize attribute vs dict access
        score = getattr(hit, "_score", None) or hit.get("_score", 0.0)
        fields = getattr(hit, "fields", None) or hit.get("fields", {})
        print(f"\n--- Hit {i + 1}  score={score:.3f} ---")
        for k in [
            "ticker",
            "company",
            "report_type",
            "generated_date",
            "section",
            "signal",
            "grade",
            "composite_score",
        ]:
            val = fields.get(k) if hasattr(fields, "get") else getattr(fields, k, None)
            if val is not None:
                print(f"  {k:>17}: {val}")
        text = (
            fields.get("text")
            if hasattr(fields, "get")
            else getattr(fields, "text", "")
        ) or ""
        snippet = text.replace("\n", " ")[:240]
        print(f"  {'text':>17}: {snippet}{'…' if len(text) > 240 else ''}")
    return 0


# ---------------------------------------------------------------------------
# Slice 3b subcommands — latest / list / timeline / delete / rebuild /
# recommend-tier / doctor
# ---------------------------------------------------------------------------


def _select_latest_meta(store: "VectorStore", ticker: str, report_type: str = None):
    """Find the newest record for ``ticker`` (optionally filtered to a
    report_type), fetch one chunk's metadata, and return it. Returns None if
    no records exist.

    Strategy: list-by-prefix → pick the largest timestamp → fetch one of its
    IDs. IDs being lexically sortable on the YYYYMMDD-HHMM component is what
    makes this O(N) over the matched prefix without a sort.
    """
    prefix = f"{ticker}:" if not report_type else f"{ticker}:{report_type}:"
    all_ids = list(store.list_ids(prefix=prefix))
    if not all_ids:
        return None
    # If --type was not passed, restrict to ANALYSIS for tier decisions — but
    # callers wanting "newest of any type" should pass an explicit type. Here
    # we leave the filtering to the caller; pick the lexically max ID.
    newest_ts = _newest_timestamp(all_ids)
    if newest_ts is None:
        return None
    candidates = [i for i in all_ids if _parse_id(i) and _parse_id(i)[2] == newest_ts]
    # Fetch just one — all chunks of one report share their identification
    # metadata (only section/chunk_index/text differ).
    meta_by_id = store.fetch_meta(candidates[:1])
    if not meta_by_id:
        return None
    return next(iter(meta_by_id.values()))


def cmd_latest(args):
    store = VectorStore(namespace=args.namespace)
    meta = _select_latest_meta(store, args.ticker, args.type)
    if meta is None:
        print("{}")
        return 0
    print(json.dumps(_meta_display(meta), indent=2, sort_keys=True, default=str))
    return 0


def cmd_list(args):
    """Manifest: one line per matching record. Default limit 100 keeps output
    paste-friendly on large namespaces.
    """
    store = VectorStore(namespace=args.namespace)
    # Pick the most selective prefix the filters allow
    if args.ticker and args.type:
        prefix = f"{args.ticker}:{args.type}:"
    elif args.ticker:
        prefix = f"{args.ticker}:"
    else:
        prefix = None

    ids = []
    for rid in store.list_ids(prefix=prefix):
        # --type without --ticker: filter post-list since Pinecone has no
        # type-only prefix path (ticker comes first in the ID grammar).
        if args.type and not args.ticker:
            parsed = _parse_id(rid)
            if not parsed or parsed[1] != args.type:
                continue
        ids.append(rid)
        if len(ids) >= args.limit:
            break

    if not ids:
        print("(no records)")
        return 0

    meta_by_id = store.fetch_meta(ids)
    for rid in ids:
        meta = meta_by_id.get(rid, {})
        print(
            f"{rid}\t"
            f"signal={meta.get('signal', '-')}\t"
            f"grade={meta.get('grade', '-')}\t"
            f"score={meta.get('composite_score', '-')}\t"
            f"date={_display_date(meta)}\t"
            f"section={meta.get('section', '-')}"
        )
    print(f"\n{len(ids)} record(s) listed.", file=sys.stderr)
    return 0


def cmd_timeline(args):
    """All records for a ticker, oldest→newest, filtered by --since."""
    store = VectorStore(namespace=args.namespace)
    # Default --since: 12 months back from today (UTC).
    if args.since is None:
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=365)).date()
    else:
        try:
            cutoff_date = datetime.strptime(args.since, "%Y-%m-%d").date()
        except ValueError:
            print(
                f"[error] --since must be YYYY-MM-DD; got {args.since!r}",
                file=sys.stderr,
            )
            return 1

    ids = list(store.list_ids(prefix=f"{args.ticker}:"))
    if not ids:
        print(f"(no records for {args.ticker})")
        return 0

    # Lexical sort on the full ID == sort by (type, timestamp, section, chunk)
    # which interleaves types. Resort on the timestamp component to interleave
    # cleanly across report types.
    def _ts(rid):
        parsed = _parse_id(rid)
        return parsed[2] if parsed else "00000000-0000"

    ids.sort(key=_ts)

    meta_by_id = store.fetch_meta(ids[: args.limit * 4])  # buffer for filtering
    rows = []
    for rid in ids:
        meta = meta_by_id.get(rid, {})
        gen_date = meta.get("generated_date") or ""
        if gen_date:
            try:
                if datetime.strptime(gen_date, "%Y-%m-%d").date() < cutoff_date:
                    continue
            except ValueError:
                pass  # tolerate malformed dates; show the record
        rows.append((rid, meta))
        if len(rows) >= args.limit:
            break

    if not rows:
        print(f"(no records for {args.ticker} since {cutoff_date})")
        return 0

    # Group by report timestamp (one row per report, not per chunk)
    seen_ts = set()
    for rid, meta in rows:
        parsed = _parse_id(rid)
        if not parsed:
            continue
        ts = parsed[2]
        if ts in seen_ts:
            continue
        seen_ts.add(ts)
        print(
            f"{_display_date(meta)}\t"
            f"{parsed[1]:>10}\t"
            f"signal={meta.get('signal', '-')}\t"
            f"grade={meta.get('grade', '-')}\t"
            f"score={meta.get('composite_score', '-')}\t"
            f"id={rid}"
        )
    print(
        f"\n{len(seen_ts)} report(s) for {args.ticker} since {cutoff_date}.",
        file=sys.stderr,
    )
    return 0


def cmd_delete(args):
    """GC for a ticker. Confirms unless --yes. ``--before YYYY-MM-DD`` keeps
    records dated on/after that boundary; rest go.
    """
    store = VectorStore(namespace=args.namespace)
    ids = list(store.list_ids(prefix=f"{args.ticker}:"))
    if not ids:
        print(f"(no records for {args.ticker})")
        return 0

    # --before filter requires metadata; if absent, delete everything for the
    # ticker.
    targets = ids
    if args.before:
        try:
            cutoff_date = datetime.strptime(args.before, "%Y-%m-%d").date()
        except ValueError:
            print(
                f"[error] --before must be YYYY-MM-DD; got {args.before!r}",
                file=sys.stderr,
            )
            return 1
        meta_by_id = store.fetch_meta(ids)
        targets = []
        for rid in ids:
            gen_date = (meta_by_id.get(rid, {}) or {}).get("generated_date")
            if not gen_date:
                # No date → conservatively skip (don't blow away records we
                # can't classify).
                continue
            try:
                if datetime.strptime(gen_date, "%Y-%m-%d").date() < cutoff_date:
                    targets.append(rid)
            except ValueError:
                continue

    if not targets:
        print(
            f"(no records for {args.ticker} match the filter; nothing to delete)"
        )
        return 0

    if not args.yes:
        sys.stderr.write(
            f"About to delete {len(targets)} record(s) for {args.ticker} "
            f"from namespace '{store.namespace}'.\n"
            f"Pass --yes to proceed, or Ctrl-C to abort.\n"
        )
        try:
            confirm = input("Type the ticker to confirm: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n(aborted)", file=sys.stderr)
            return 1
        if confirm != args.ticker:
            print("(ticker mismatch; aborted)", file=sys.stderr)
            return 1

    deleted = store.delete_ids(targets)
    print(
        f"Deleted {deleted} record(s) for {args.ticker} "
        f"from namespace '{store.namespace}'."
    )
    return 0


def cmd_rebuild(args):
    """Re-ingest every TRADE-*.md under <source>. Local directories only —
    Drive folder IDs are out of scope for the Python script (MCP-tool calls
    only run inside the LLM/skill context). See module docstring.
    """
    store = VectorStore(namespace=args.namespace)
    exclude = set()
    if args.exclude_ticker:
        exclude = {t.strip().upper() for t in args.exclude_ticker.split(",") if t.strip()}

    source = pathlib.Path(args.source).expanduser()
    if not source.exists() or not source.is_dir():
        # If it doesn't look like a path, the user probably passed a Drive
        # folder ID. Point them at the equivalent skill-side flow.
        if "/" not in args.source and "\\" not in args.source:
            print(
                f"[error] rebuild expects a local directory; got {args.source!r}, "
                "which doesn't exist as a path.\n"
                "  Drive-folder rebuild requires the Google_Drive MCP tools, "
                "which Python can't invoke directly.\n"
                "  Workflow: have the calling skill list & download the Drive "
                "folder's TRADE-*.md files into a local directory, then point "
                "rebuild at that directory.",
                file=sys.stderr,
            )
            return 2
        print(
            f"[error] rebuild source not found or not a directory: {source}",
            file=sys.stderr,
        )
        return 1

    files = sorted(source.glob("TRADE-*.md"))
    if not files:
        print(f"[warn] no TRADE-*.md files under {source}", file=sys.stderr)
        return 0

    total_chunks = 0
    skipped = 0
    for fp in files:
        try:
            records = parse_report(str(fp))
        except Exception as e:
            print(f"[warn] {fp.name}: parse failed ({e}); skipping", file=sys.stderr)
            continue
        if not records:
            continue
        ticker = records[0].ticker
        if ticker in exclude:
            skipped += 1
            print(f"  - {fp.name}: skipped (ticker {ticker} excluded)", file=sys.stderr)
            continue
        first = records[0]
        ts = first.generated_at_compact()
        for rec in records:
            rec.id = (
                f"{rec.ticker}:{rec.report_type}:{ts}"
                f":{rec.section}:{rec.chunk_index}"
            )
        store.upsert_records(records)
        total_chunks += len(records)
        print(
            f"  + {fp.name}: {len(records)} chunk(s) → namespace '{store.namespace}'",
            file=sys.stderr,
        )

    print(
        f"Rebuilt {total_chunks} chunk(s) from {len(files) - skipped} file(s) "
        f"({skipped} excluded) under {source}."
    )
    return 0


def cmd_recommend_tier(args):
    """Tier the next sweep. Rules per plan §1:
        analyze   no prior ANALYSIS, OR catalyst within 14 days,
                  OR last full analysis > 30 days old, OR Pinecone unavailable
        quick     otherwise

    Pinecone-unavailable → prints `analyze` and exits 0 with a stderr warning
    (NOT a non-zero exit; the routine must keep running). This is the
    explicit safe-default contract from the spec.
    """
    try:
        store = VectorStore(namespace=args.namespace)
        # Force credential check up-front so we surface the "memory unknown"
        # branch before issuing any RPCs.
        _ = store.index  # triggers _require_local_creds + Pinecone client init
        meta = _select_latest_meta(store, args.ticker, report_type="ANALYSIS")
    except SystemExit:
        # _require_local_creds calls sys.exit on missing key; intercept so
        # recommend-tier itself stays exit 0 per spec.
        print("analyze")
        sys.stderr.write(
            "[warn] recommend-tier: Pinecone unavailable "
            "(missing/invalid PINECONE_API_KEY); defaulted to analyze.\n"
        )
        return 0
    except Exception as e:
        print("analyze")
        sys.stderr.write(
            f"[warn] recommend-tier: Pinecone error ({e}); defaulted to analyze.\n"
        )
        return 0

    if not meta:
        # No prior ANALYSIS → analyze
        print("analyze")
        return 0

    today = datetime.now(timezone.utc).date()

    # Rule: catalyst within 14 days → analyze
    nearest = meta.get("nearest_catalyst_date")
    if nearest:
        try:
            cat_date = datetime.strptime(str(nearest), "%Y-%m-%d").date()
            if 0 <= (cat_date - today).days <= 14:
                print("analyze")
                return 0
        except ValueError:
            pass  # malformed catalyst date — fall through to age check

    # Rule: last analysis > 30 days old → analyze
    # Backfill from generated_at for legacy records ingested before the
    # parse_report `generated_date` derivation landed (slice 3a fixture data).
    gen_date = meta.get("generated_date")
    if not gen_date and meta.get("generated_at"):
        gen_date = str(meta["generated_at"])[:10]
    if gen_date:
        try:
            g_date = datetime.strptime(str(gen_date), "%Y-%m-%d").date()
            if (today - g_date).days > 30:
                print("analyze")
                return 0
        except ValueError:
            # No reliable date — safer to escalate than to skip
            print("analyze")
            sys.stderr.write(
                f"[warn] recommend-tier {args.ticker}: malformed generated_date "
                f"({gen_date!r}); defaulted to analyze.\n"
            )
            return 0
    else:
        # Newest record has no date metadata — escalate
        print("analyze")
        return 0

    print("quick")
    return 0


def cmd_doctor(args):
    """Health check. Exit codes:
        0 — healthy: SDK present, key present, index exists, vectors > 0,
            embedding model matches PINECONE_EMBED_MODEL, archive folder set.
        1 — degraded: missing optional Drive folder ID, embedding-model drift,
            or empty index.
        2 — unavailable: SDK missing, key missing, or index missing.
    """
    severity = 0  # 0 healthy, 1 degraded, 2 unavailable
    lines = []

    def _line(symbol, msg):
        lines.append(f"  {symbol} {msg}")

    def _escalate(level):
        nonlocal severity
        if level > severity:
            severity = level

    # 1. SDK
    try:
        from pinecone import Pinecone  # noqa: F401
        _line("✓", "Pinecone SDK importable (`pinecone`)")
    except ImportError:
        _line("✗", "Pinecone SDK missing — run `pip install 'pinecone>=5'`")
        _escalate(2)
        # No point continuing the checks that depend on the SDK
        _emit_doctor_report(severity, lines)
        return severity

    # 2. Credentials — branch on local vs cloud (proxy) mode
    proxy_url = os.environ.get("PINECONE_PROXY_URL")
    proxy_token = os.environ.get("PINECONE_PROXY_TOKEN")
    proxy_mode = bool(proxy_url and proxy_token)

    if proxy_mode:
        _line(
            "✓",
            f"Cloud-proxy mode active — routing via {proxy_url}",
        )
        # Auth probe: POST /query with an empty payload, expect HTTP 400
        # (validation_failed because no namespace/text). 401 means bearer
        # is wrong; network errors mean URL/connectivity broken.
        store = VectorStore(namespace=args.namespace)
        try:
            store._proxy_post("query", {})
            # If we somehow got 200 with an empty payload, the proxy is
            # mis-configured. Report as degraded.
            _line(
                "⚠",
                "Proxy returned 200 on an empty /query payload — proxy "
                "validation is weaker than expected. Check deployed code.",
            )
            _escalate(1)
        except ProxyHTTPError as e:
            if e.status_code == 400:
                _line(
                    "✓",
                    "Proxy auth check passed (POST /query returned 400 "
                    "validation_failed on empty payload — bearer + URL ok)",
                )
            elif e.status_code == 401:
                _line(
                    "✗",
                    "Proxy bearer auth FAILED (401) — "
                    "check PINECONE_PROXY_TOKEN matches the deployed "
                    "PROXY_AUTH_TOKEN Vercel env var.",
                )
                _escalate(2)
                _emit_doctor_report(severity, lines)
                return severity
            elif e.status_code == 429:
                _line(
                    "⚠",
                    "Proxy rate-limited (429) — this is unusual on the auth "
                    "check; the per-IP counter may be saturated.",
                )
                _escalate(1)
            elif e.status_code == 403:
                proxy_host = proxy_url.split("://")[-1].split("/")[0]
                _line(
                    "✗",
                    f"Proxy BLOCKED (403) before reaching the function: "
                    f"{e.body}. The proxy app never emits 403, so this is an "
                    "egress/firewall ALLOWLIST denial, not an auth problem. In "
                    "a cloud routine it's the Claude sandbox egress proxy: add "
                    f"`{proxy_host}` to the routine environment's Network "
                    "access → Custom → Allowed domains (code.claude.com/docs/"
                    "en/claude-code-on-the-web §Network access). From a "
                    "workstation, check Vercel firewall / Trusted-IPs rules.",
                )
                _escalate(2)
                _emit_doctor_report(severity, lines)
                return severity
            else:
                _line(
                    "⚠",
                    f"Proxy auth check returned HTTP {e.status_code}: "
                    f"{e.body}. Investigate proxy logs.",
                )
                _escalate(1)
        # Skip admin-op probes (index_exists, describe, stats) — the proxy
        # intentionally doesn't expose them. Doctor in cloud mode is a
        # reachability + auth check only.
        if os.environ.get("TRADE_DRIVE_ARCHIVE_FOLDER_ID"):
            _line("✓", "TRADE_DRIVE_ARCHIVE_FOLDER_ID set")
        else:
            _line(
                "⚠",
                "TRADE_DRIVE_ARCHIVE_FOLDER_ID unset — "
                "`ingest --archive` will skip Drive uploads",
            )
            _escalate(1)
        _emit_doctor_report(severity, lines)
        return severity

    if not os.environ.get("PINECONE_API_KEY"):
        _line(
            "✗",
            "PINECONE_API_KEY not set — `cp .env.example .env`, paste key, "
            "`set -a; source .env; set +a` (or set PINECONE_PROXY_URL + "
            "PINECONE_PROXY_TOKEN for cloud-proxy mode)",
        )
        _escalate(2)
        _emit_doctor_report(severity, lines)
        return severity
    _line("✓", "PINECONE_API_KEY present")

    # 3+. Live index checks (only safe to do once SDK + key are in hand)
    store = VectorStore(namespace=args.namespace)
    try:
        if not store.index_exists():
            _line(
                "✗",
                f"Index '{store.index_name}' does not exist — run "
                "`trade_memory.py init`",
            )
            _escalate(2)
            _emit_doctor_report(severity, lines)
            return severity
        _line("✓", f"Index '{store.index_name}' exists in {store.cloud}/{store.region}")

        # Embedding-model drift check (warn-only; don't fail loudly)
        try:
            idx_model = store.describe_index()
            embed_info = getattr(idx_model, "embed", None) or {}
            stored_model = embed_info.get("model") if hasattr(embed_info, "get") else (
                getattr(embed_info, "model", None)
            )
            if stored_model and stored_model != store.embed_model:
                _line(
                    "⚠",
                    f"Embedding-model drift: index='{stored_model}' vs "
                    f"PINECONE_EMBED_MODEL='{store.embed_model}'. New ingests "
                    "will use the index's model; queries should match.",
                )
                _escalate(1)
            elif stored_model:
                _line("✓", f"Embedding model: {stored_model}")
        except Exception as e:
            _line("⚠", f"Could not read index embedding-model spec ({e})")
            _escalate(1)

        # Vector counts
        try:
            stats = store.describe_stats()
            namespaces = stats.namespaces if hasattr(stats, "namespaces") else (
                stats.get("namespaces", {})
            )
            ns_info = namespaces.get(store.namespace) if hasattr(namespaces, "get") else None
            count = 0
            if ns_info is not None:
                count = (
                    getattr(ns_info, "vector_count", None)
                    if not hasattr(ns_info, "get")
                    else ns_info.get("vector_count", 0)
                ) or 0
            total = getattr(stats, "total_vector_count", None) or (
                stats.get("total_vector_count", 0) if hasattr(stats, "get") else 0
            )
            if count == 0:
                _line(
                    "⚠",
                    f"Namespace '{store.namespace}' is empty "
                    f"({total} vectors across all namespaces). "
                    "Run `ingest` or `rebuild` to populate.",
                )
                _escalate(1)
            else:
                _line(
                    "✓",
                    f"Namespace '{store.namespace}': {count} vector(s) "
                    f"({total} across all namespaces)",
                )
        except Exception as e:
            _line("⚠", f"Could not read index stats ({e})")
            _escalate(1)

    except Exception as e:
        _line("✗", f"Live index check failed ({e})")
        _escalate(2)
        _emit_doctor_report(severity, lines)
        return severity

    # 4. Drive archive folder ID (optional but flagged)
    if os.environ.get("TRADE_DRIVE_ARCHIVE_FOLDER_ID"):
        _line(
            "✓",
            "TRADE_DRIVE_ARCHIVE_FOLDER_ID set "
            "(value hidden; --archive will request Drive uploads via the skill)",
        )
    else:
        _line(
            "⚠",
            "TRADE_DRIVE_ARCHIVE_FOLDER_ID unset — `ingest --archive` will "
            "emit a setup hint and skip the Drive upload. Set this to enable "
            "Drive mirroring.",
        )
        _escalate(1)

    # 5. Drive MCP availability — Python can't introspect this, surface it
    _line(
        "?",
        "Drive MCP availability: not detectable from Python. "
        "If the skill has access to `mcp__claude_ai_Google_Drive__*` tools, "
        "archive uploads will work.",
    )

    # 6. Proxy env vars set but incomplete
    if os.environ.get("PINECONE_PROXY_URL") and not os.environ.get("PINECONE_PROXY_TOKEN"):
        _line(
            "⚠",
            "PINECONE_PROXY_URL set but PINECONE_PROXY_TOKEN missing — "
            "cloud-proxy mode requires both. Using local SDK.",
        )
        _escalate(1)
    elif os.environ.get("PINECONE_PROXY_TOKEN") and not os.environ.get("PINECONE_PROXY_URL"):
        _line(
            "⚠",
            "PINECONE_PROXY_TOKEN set but PINECONE_PROXY_URL missing — "
            "cloud-proxy mode requires both. Using local SDK.",
        )
        _escalate(1)

    _emit_doctor_report(severity, lines)
    return severity


def _emit_doctor_report(severity: int, lines):
    state = {0: "HEALTHY", 1: "DEGRADED", 2: "UNAVAILABLE"}[severity]
    print(f"trade_memory.py doctor — {state}")
    for ln in lines:
        print(ln)


# ---------------------------------------------------------------------------
# argparse plumbing
# ---------------------------------------------------------------------------


def build_parser():
    p = argparse.ArgumentParser(
        prog="trade_memory.py",
        description=__doc__.split("\n")[1],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--namespace",
        metavar="NS",
        help=(
            "Override PINECONE_NAMESPACE for this invocation. Plumbed into "
            "every subcommand; writes additionally require the namespace to "
            "be in trade_schemas.ALLOWED_NAMESPACES (currently 'trade'). "
            "The trading-chatbot will register per-user namespaces in "
            "slice 7.5."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser(
        "init",
        help="Create the Pinecone integrated-inference index (idempotent).",
    )
    p_init.set_defaults(func=cmd_init)

    p_ingest = sub.add_parser(
        "ingest",
        help="Parse a TRADE-*.md report and upsert its chunks.",
    )
    p_ingest.add_argument("file", help="Path to a TRADE-*.md report file")
    p_ingest.add_argument(
        "--run-id",
        help=(
            "Tag every chunk with this run_id (used by /trade routine sweeps; "
            "format: routine-<YYYYMMDD-HHMM>-<6hex>)."
        ),
    )
    p_ingest.add_argument(
        "--archive",
        action="store_true",
        help=(
            "Also mirror the report to Drive under "
            "<TRADE_DRIVE_ARCHIVE_FOLDER_ID>/<TICKER>/<basename>. "
            "Emits a [archive-todo] JSON line on stderr that the calling "
            "skill executes via Google_Drive MCP tools; Python cannot invoke "
            "MCP directly. If the env var is unset, prints a setup hint and "
            "skips Drive (Pinecone upsert still succeeds)."
        ),
    )
    p_ingest.set_defaults(func=cmd_ingest)

    p_query = sub.add_parser(
        "query",
        help="Integrated-inference semantic search over stored reports.",
    )
    p_query.add_argument("text", help="Query text")
    p_query.add_argument("--ticker", help="Filter to a single ticker")
    p_query.add_argument(
        "--type",
        help="Filter to a single report_type (ANALYSIS/THESIS/...)",
    )
    p_query.add_argument(
        "-n", type=int, default=5, help="Top-K hits (default 5)"
    )
    p_query.set_defaults(func=cmd_query)

    # --- slice 3b subcommands ---

    p_latest = sub.add_parser(
        "latest",
        help="Newest record's metadata as JSON (filtered by --type).",
    )
    p_latest.add_argument("ticker", help="Ticker symbol (UPPERCASE)")
    p_latest.add_argument(
        "--type",
        help="Filter to a single report_type (ANALYSIS/THESIS/QUICK/...)",
    )
    p_latest.set_defaults(func=cmd_latest)

    p_list = sub.add_parser(
        "list",
        help="Manifest listing across the namespace (default limit 100).",
    )
    p_list.add_argument("--ticker", help="Filter to a single ticker")
    p_list.add_argument(
        "--type", help="Filter to a single report_type"
    )
    p_list.add_argument(
        "--limit", type=int, default=100, help="Max records to print (default 100)"
    )
    p_list.set_defaults(func=cmd_list)

    p_timeline = sub.add_parser(
        "timeline",
        help="All reports for a ticker, oldest→newest.",
    )
    p_timeline.add_argument("ticker", help="Ticker symbol (UPPERCASE)")
    p_timeline.add_argument(
        "--since",
        help="Cutoff date (YYYY-MM-DD); defaults to 12 months ago",
    )
    p_timeline.add_argument(
        "--limit", type=int, default=50, help="Max reports to show (default 50)"
    )
    p_timeline.set_defaults(func=cmd_timeline)

    p_delete = sub.add_parser(
        "delete",
        help="GC records for a ticker. Confirms unless --yes.",
    )
    p_delete.add_argument("--ticker", required=True, help="Ticker to delete")
    p_delete.add_argument(
        "--before",
        help=(
            "Only delete records dated strictly before YYYY-MM-DD "
            "(keeps newer records)"
        ),
    )
    p_delete.add_argument(
        "--yes", action="store_true", help="Skip the interactive confirmation"
    )
    p_delete.set_defaults(func=cmd_delete)

    p_rebuild = sub.add_parser(
        "rebuild",
        help="Re-ingest every TRADE-*.md under a local directory.",
    )
    p_rebuild.add_argument(
        "source",
        help=(
            "Local directory containing TRADE-*.md files. "
            "Drive folder IDs are NOT supported here — Python cannot call "
            "the Drive MCP tools; have the calling skill download to a local "
            "dir first."
        ),
    )
    p_rebuild.add_argument(
        "--exclude-ticker",
        help="Comma-separated tickers to skip (e.g. tickers that left the portfolio)",
    )
    p_rebuild.set_defaults(func=cmd_rebuild)

    p_tier = sub.add_parser(
        "recommend-tier",
        help=(
            "Print 'analyze' or 'quick' for the next sweep. "
            "Pinecone-unavailable safely prints 'analyze' and exits 0."
        ),
    )
    p_tier.add_argument("ticker", help="Ticker symbol (UPPERCASE)")
    p_tier.set_defaults(func=cmd_recommend_tier)

    p_doctor = sub.add_parser(
        "doctor",
        help=(
            "Health check. Exit 0 healthy / 1 degraded / 2 unavailable."
        ),
    )
    p_doctor.set_defaults(func=cmd_doctor)

    return p


def main():
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
