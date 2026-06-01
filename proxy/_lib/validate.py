"""Payload validation for the AI Trading Analyst proxy.

Layer 3 of the 5-layer auth model. Schema lockdown is the structural defense
even if the bearer leaks: an attacker can only write contract-valid records
to allowed namespaces.

Imports the canonical ``RecordMetadata`` + ``ALLOWED_NAMESPACES`` +
``RECORD_ID_PATTERN`` from ``scripts/trade_schemas.py`` so the proxy
boundary stays in lockstep with what the producer writes (D.17 +
D.19 gates).

Single-source-of-truth resolution: at Vercel runtime,
``scripts/trade_schemas.py`` is bundled into the function via
``vercel.json``'s ``includeFiles``; we locate it via
``importlib.util.spec_from_file_location`` so the import works regardless
of sys.path quirks.
"""

import importlib.util
import os
import pathlib
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# trade_schemas import — finds the bundled file at deploy time
# ---------------------------------------------------------------------------

def _import_trade_schemas():
    """Locate scripts/trade_schemas.py and import it as ``trade_schemas``.

    Search order:
    1. ``TRADE_SCHEMAS_PATH`` env var (deploy-time override)
    2. ``/var/task/scripts/trade_schemas.py`` (Vercel runtime layout when
       vercel.json's includeFiles bundles ../scripts/trade_schemas.py)
    3. ``<this file's grandparent>/scripts/trade_schemas.py`` (repo-local
       dev: proxy/_lib/validate.py → ai-trading-claude/scripts/...)
    """
    candidates = []
    env_path = os.environ.get("TRADE_SCHEMAS_PATH")
    if env_path:
        candidates.append(pathlib.Path(env_path))
    candidates.append(pathlib.Path("/var/task/scripts/trade_schemas.py"))
    here = pathlib.Path(__file__).resolve()
    candidates.append(here.parent.parent.parent / "scripts" / "trade_schemas.py")

    for path in candidates:
        if path.exists():
            spec = importlib.util.spec_from_file_location("trade_schemas", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod

    raise ImportError(
        "Could not locate scripts/trade_schemas.py. Set TRADE_SCHEMAS_PATH "
        "or check vercel.json includeFiles."
    )


trade_schemas = _import_trade_schemas()
RecordMetadata = trade_schemas.RecordMetadata
ALLOWED_NAMESPACES = trade_schemas.ALLOWED_NAMESPACES
RECORD_ID_PATTERN = trade_schemas.RECORD_ID_PATTERN
SCHEMA_VERSION = trade_schemas.SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


class ValidationError(Exception):
    """Raised when a payload fails validation. Maps to HTTP 400."""

    def __init__(self, reason: str, details: dict = None):
        super().__init__(reason)
        self.reason = reason
        self.details = details or {}


def check_namespace(namespace: Optional[str]) -> str:
    """Return the namespace if allowed, raise ``ValidationError`` otherwise.

    Defense for both writes AND reads — even read-only ops are restricted
    to the allowlist so a leaked bearer can't enumerate consumer
    namespaces the proxy wasn't designed to serve.
    """
    if not namespace:
        raise ValidationError(
            "namespace required",
            {"hint": f"valid: {sorted(ALLOWED_NAMESPACES)}"},
        )
    if not trade_schemas.is_allowed_namespace(namespace):
        raise ValidationError(
            f"namespace {namespace!r} not in allowlist",
            {"allowed": sorted(ALLOWED_NAMESPACES)},
        )
    return namespace


# ---------------------------------------------------------------------------
# Per-endpoint Pydantic request schemas
# ---------------------------------------------------------------------------


class UpsertRequest(BaseModel):
    """``POST /upsert`` payload. Max 100 records per call. Records with
    ``text`` set + ``values`` absent → integrated-inference path.
    """

    model_config = ConfigDict(extra="forbid")

    namespace: str
    records: List[dict] = Field(min_length=1, max_length=100)

    @field_validator("records")
    @classmethod
    def _validate_records(cls, records):
        for i, rec in enumerate(records):
            # Re-validate via the canonical RecordMetadata model. We don't
            # bind to it directly here because RecordMetadata's _id (lifted
            # from `id` at to_pinecone_record time) requires the pre-lifted
            # field name. Accept either `id` or `_id` from the caller.
            normalized = dict(rec)
            if "_id" in normalized and "id" not in normalized:
                normalized["id"] = normalized.pop("_id")
            try:
                RecordMetadata(**normalized)
            except Exception as e:
                raise ValueError(
                    f"records[{i}]: schema violation — {e}"
                )
        return records


class QueryRequest(BaseModel):
    """``POST /query`` payload. Either ``text`` (integrated-inference) or
    ``vector`` (pre-embedded). ``top_k`` capped at 50.
    """

    model_config = ConfigDict(extra="forbid")

    namespace: str
    text: Optional[str] = None
    vector: Optional[List[float]] = None
    top_k: int = Field(default=5, ge=1, le=50)
    filter: Optional[dict] = None

    @field_validator("filter")
    @classmethod
    def _filter_keys_known(cls, v):
        if v is None:
            return v
        # Reject filters referencing unknown metadata keys. We allow Pinecone
        # operators ($eq, $in, etc.) at the value level but the top-level
        # keys must be schema fields.
        known = set(RecordMetadata.model_fields.keys()) | {"_id"}
        for key in v.keys():
            if key not in known:
                raise ValueError(
                    f"filter references unknown field {key!r}; allowed: "
                    f"{sorted(known)}"
                )
        return v


class ListRequest(BaseModel):
    """``POST /list`` payload. Prefix required (lexical-scope guard).
    ``limit`` capped at 1000.
    """

    model_config = ConfigDict(extra="forbid")

    namespace: str
    prefix: str = Field(min_length=1)
    limit: int = Field(default=100, ge=1, le=1000)
    pagination_token: Optional[str] = None


class FetchRequest(BaseModel):
    """``POST /fetch`` payload. Max 100 ids per call."""

    model_config = ConfigDict(extra="forbid")

    namespace: str
    ids: List[str] = Field(min_length=1, max_length=100)

    @field_validator("ids")
    @classmethod
    def _ids_match_pattern(cls, ids):
        for i, rid in enumerate(ids):
            if not RECORD_ID_PATTERN.match(rid):
                raise ValueError(
                    f"ids[{i}]={rid!r} doesn't match the record-id contract"
                )
        return ids


class DeleteRequest(BaseModel):
    """``POST /delete`` payload. ``confirm: "yes"`` is REQUIRED — bulk
    delete must be an explicit action.
    """

    model_config = ConfigDict(extra="forbid")

    namespace: str
    ids: Optional[List[str]] = None
    filter: Optional[dict] = None
    confirm: str

    @field_validator("confirm")
    @classmethod
    def _confirm_yes(cls, v):
        if v != "yes":
            raise ValueError(
                'delete requires confirm="yes" (received: ' + repr(v) + ")"
            )
        return v

    @field_validator("ids")
    @classmethod
    def _ids_capped(cls, ids):
        if ids and len(ids) > 1000:
            raise ValueError("ids list capped at 1000 per call")
        return ids
