#!/usr/bin/env python3
"""
trade_memory.py — Memory engine for the AI Trading Analyst plugin.

Vector store interface over Pinecone (serverless, integrated inference).

* Single source of truth for the record schema: ``scripts/trade_schemas.py``
* Shared scoring helpers (legacy parser): ``scripts/trade_scoring.py``

Slice 3a (this slice) ships:
    init          Create the integrated-inference index (idempotent)
    ingest        Parse a TRADE-*.md report and upsert its chunks
    query         Semantic search over stored reports

Slice 3b will add:
    recommend-tier, timeline, list, rebuild, delete, doctor
    Drive archive helper (--archive flag on ingest)
    Top-level --namespace flag plumbed everywhere

Slice 7.5 will wire:
    Cloud-mode auto-detect via PINECONE_PROXY_URL + PINECONE_PROXY_TOKEN
    (the VectorStore class is already structured for it; the cloud branch
    currently exits with a "not yet implemented" message)

See ``plan/portfolio-routine-and-vector-memory.md`` §1 for the full spec.

Usage
-----

::

    # Local (slice 3a):
    export PINECONE_API_KEY=pcsk_...
    python3 scripts/trade_memory.py init
    python3 scripts/trade_memory.py ingest TRADE-ANALYSIS-AAPL.md
    python3 scripts/trade_memory.py query "bull case for apple" --ticker AAPL -n 5
"""

import argparse
import importlib.util
import json
import os
import pathlib
import re
import sys
from datetime import datetime, timezone


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
        if self._proxy_mode:
            sys.exit(
                "Cloud proxy mode (PINECONE_PROXY_URL set) is not yet "
                "implemented — slice 7.5 deliverable. For now, unset "
                "PINECONE_PROXY_URL and use PINECONE_API_KEY directly."
            )
        if not self.api_key:
            sys.exit(
                "PINECONE_API_KEY is not set. Copy .env.example to .env, "
                "fill in your Pinecone key, and `set -a; source .env; set +a` "
                "before running this command."
            )

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

        Pinecone's ``Index.upsert_records(namespace, records)`` is the
        integrated-inference path — server-side embedding from the ``text``
        field, no client-side vectors required.
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
        payload = [r.to_pinecone_record() for r in records]
        return self.index.upsert_records(self.namespace, payload)

    def query(self, text: str, top_k: int = 5, filter_dict: dict = None):
        """Integrated-inference semantic search. Returns the raw
        ``SearchRecordsResponse``; callers handle pretty-printing.
        """
        q = {"inputs": {"text": text}, "top_k": top_k}
        if filter_dict:
            q["filter"] = filter_dict
        return self.index.search(namespace=self.namespace, query=q)


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
    return 0


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
            "Override PINECONE_NAMESPACE for this invocation. "
            "Slice 3a only honors 'trade'; slice 3b/7.5 will expand the "
            "allowlist for consumer namespaces."
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

    return p


def main():
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
