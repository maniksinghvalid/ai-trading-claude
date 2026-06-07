#!/usr/bin/env python3
"""
trade_schemas.py — Pydantic schemas for the Pinecone record (the public contract).

Imported by:
- `scripts/trade_memory.py` (write path) — validates every record before upsert
- `proxy/_lib/validate.py` (slice 7.5+) — same validation at the proxy boundary
- D.17 schema-contract regression gate — verifies docs vs code parity

The Consumer Integration contract is documented in two mirrored tables that must
stay in lockstep with the models below:
- `plan/portfolio-routine-and-vector-memory.md` §1 "Field-contract table"
- `plan/trading-chatbot.md` "Required metadata fields per record" table

Schema versioning (per the producer-plan stability rules):
- `SCHEMA_VERSION` is bumped on **breaking changes only** (field rename, type
  change, enum-value removal).
- Additive changes (new optional fields, new enum values) do NOT bump it.
- Consumers SHOULD validate `schema_version` on read and refuse unknown majors.

This module must remain importable in a clean virtualenv with only `pydantic`
installed (no pinecone, no project sys.path tricks). See slice 3a gate.
"""

import re
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Enums — the public-contract value spaces
# ---------------------------------------------------------------------------


class Signal(str, Enum):
    """Composite trade signal. Exactly 6 values. UPPERCASE in metadata storage.

    Mirrored in `trade/SKILL.md:57-64` (mixed-case prose) and the per-dim agent
    files (which deliberately use DIFFERENT labels for per-dim scoring; see the
    slice-1 admonition blocks).
    """

    STRONG_BUY = "STRONG BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    NEUTRAL = "NEUTRAL"
    CAUTION = "CAUTION"
    AVOID = "AVOID"


class Grade(str, Enum):
    """Composite trade grade. Exactly 6 single-letter values (M4 cleanup)."""

    A_PLUS = "A+"
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"


class ReportType(str, Enum):
    """Report kind. Drives the §2 frontmatter availability table."""

    ANALYSIS = "ANALYSIS"
    THESIS = "THESIS"
    TECHNICAL = "TECHNICAL"
    FUNDAMENTAL = "FUNDAMENTAL"
    SENTIMENT = "SENTIMENT"
    RISK = "RISK"
    EARNINGS = "EARNINGS"
    QUICK = "QUICK"
    OPTIONS = "OPTIONS"


class StrategyOutlook(str, Enum):
    """Options posture on an OPTIONS report — the 'manage/grow/hedge' framing.

    INCOME = premium on an existing position (covered call, CSP).
    HEDGE  = downside protection (protective put, collar).
    BULLISH/BEARISH/NEUTRAL = directional/non-directional debit/credit plays.
    """

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    INCOME = "INCOME"
    HEDGE = "HEDGE"


class PositionBias(str, Enum):
    """The holder's existing stock position that conditioned the strategy.

    Holdings yields only LONG / FLAT (InvestmentSummary has no shorts). Routine
    OPTIONS reports are always LONG; a manual /trade options on an unheld name
    is FLAT.
    """

    LONG = "LONG"
    FLAT = "FLAT"


# ---------------------------------------------------------------------------
# Allowlists + patterns (proxy boundary will re-use these in slice 7.5)
# ---------------------------------------------------------------------------

#: Namespace allowlist. Slice 7.5 will extend this when consumer namespaces
#: register; for slice 3a only ``"trade"`` is valid.
ALLOWED_NAMESPACES = frozenset({"trade"})

#: Ticker symbols: uppercase alphanumerics, dots, and hyphens (e.g. ``BRK.B``).
TICKER_PATTERN = re.compile(r"^[A-Z0-9.\-]+$")

#: Record ID grammar — part of the public contract:
#: ``<TICKER>:<TYPE>:<YYYYMMDD-HHMM>:<section-slug>:<chunk-index>``
RECORD_ID_PATTERN = re.compile(
    r"^[A-Z0-9.\-]+:[A-Z]+:\d{8}-\d{4}:[a-z0-9\-]+:\d+$"
)


def is_allowed_namespace(ns: str) -> bool:
    """Used by the proxy boundary and the local writer. Mirror this signature
    if you split the function for a future package."""
    return ns in ALLOWED_NAMESPACES


# ---------------------------------------------------------------------------
# The record model — single source of truth
# ---------------------------------------------------------------------------


class RecordMetadata(BaseModel):
    """One Pinecone record's metadata + text payload.

    Field order intentionally matches the §1 field-contract table for diff-readability.
    All score fields are int(0–100); ``risk_score`` is INVERTED (higher = safer)
    per `CLAUDE.md` cross-file contracts.
    """

    # Pydantic v2 config: forbid unknown fields so producer/consumer drift fails
    # loudly at the validation boundary rather than silently passing garbage.
    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION

    # Identification
    ticker: str
    company: Optional[str] = None
    report_type: str  # validated to be a ReportType value
    generated_at: str  # ISO-8601 with tz offset
    generated_date: Optional[str] = None  # YYYY-MM-DD; derived from generated_at

    # Scores (all int 0-100; per-type availability per plan §2)
    composite_score: Optional[int] = Field(default=None, ge=0, le=100)
    technical_score: Optional[int] = Field(default=None, ge=0, le=100)
    fundamental_score: Optional[int] = Field(default=None, ge=0, le=100)
    sentiment_score: Optional[int] = Field(default=None, ge=0, le=100)
    risk_score: Optional[int] = Field(
        default=None, ge=0, le=100
    )  # INVERTED — higher = safer
    thesis_score: Optional[int] = Field(default=None, ge=0, le=100)

    # Options posture (OPTIONS report_type only; all optional & additive)
    iv_rank: Optional[int] = Field(default=None, ge=0, le=100)
    strategy_outlook: Optional[str] = None  # validated against StrategyOutlook
    recommended_strategy: Optional[str] = None  # primary strategy name (free text)
    position_bias: Optional[str] = None  # validated against PositionBias

    # Derived labels
    signal: Optional[str] = None  # validated against Signal enum
    grade: Optional[str] = None  # validated against Grade enum

    # Price levels
    price_at_analysis: Optional[float] = None
    price_target: Optional[float] = None
    stop_loss: Optional[float] = None

    # Catalysts (stored as list in the model; comma-joined to a string at the
    # Pinecone metadata boundary because Pinecone metadata can't store native
    # heterogenous lists per the §1 schema notes)
    catalysts: Optional[List[str]] = None
    nearest_catalyst_date: Optional[str] = None

    # Provenance
    run_id: Optional[str] = None  # routine-<YYYYMMDD-HHMM>-<6hex> when applicable
    source_path: Optional[str] = None
    section: Optional[str] = None  # section slug (e.g., "executive-summary")
    chunk_index: Optional[int] = Field(default=None, ge=0)

    # Pinecone integrated-inference payload — set at upsert time
    id: Optional[str] = None
    text: Optional[str] = None

    # -----------------------------------------------------------------------
    # Validators
    # -----------------------------------------------------------------------

    @field_validator("ticker")
    @classmethod
    def _ticker_format(cls, v: str) -> str:
        if not TICKER_PATTERN.match(v):
            raise ValueError(
                f"ticker must match {TICKER_PATTERN.pattern}; got {v!r}"
            )
        return v

    @field_validator("report_type")
    @classmethod
    def _report_type_value(cls, v: str) -> str:
        valid = {t.value for t in ReportType}
        if v not in valid:
            raise ValueError(
                f"report_type must be one of {sorted(valid)}; got {v!r}"
            )
        return v

    @field_validator("signal")
    @classmethod
    def _signal_uppercase(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        valid = {s.value for s in Signal}
        if v not in valid:
            raise ValueError(
                f"signal must be one of {sorted(valid)}; got {v!r} "
                "(uppercase exactly; per Consumer Integration contract)"
            )
        return v

    @field_validator("grade")
    @classmethod
    def _grade_value(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        valid = {g.value for g in Grade}
        if v not in valid:
            raise ValueError(
                f"grade must be one of {sorted(valid)}; got {v!r} "
                "(single-letter only — no B+/C+/C-/D+; per M4 cleanup)"
            )
        return v

    @field_validator("strategy_outlook")
    @classmethod
    def _strategy_outlook_value(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        valid = {o.value for o in StrategyOutlook}
        if v not in valid:
            raise ValueError(
                f"strategy_outlook must be one of {sorted(valid)}; got {v!r}"
            )
        return v

    @field_validator("position_bias")
    @classmethod
    def _position_bias_value(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        valid = {p.value for p in PositionBias}
        if v not in valid:
            raise ValueError(
                f"position_bias must be one of {sorted(valid)}; got {v!r}"
            )
        return v

    @field_validator("id")
    @classmethod
    def _id_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not RECORD_ID_PATTERN.match(v):
            raise ValueError(
                f"id must match {RECORD_ID_PATTERN.pattern}; got {v!r}"
            )
        return v

    @field_validator("schema_version")
    @classmethod
    def _schema_version_matches(cls, v: int) -> int:
        if v != SCHEMA_VERSION:
            # We accept it but loudly warn — old records with schema_version=1
            # are fine to read; producers should always set the current version.
            # If you see this raised, it means upstream tried to write a record
            # claiming a different major. Refuse it.
            raise ValueError(
                f"schema_version mismatch: this code writes v{SCHEMA_VERSION}; "
                f"got v{v}. Refusing to ingest. Bump SCHEMA_VERSION + migrate "
                "if this is intentional."
            )
        return v

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def generated_at_compact(self) -> str:
        """Return the ``YYYYMMDD-HHMM`` portion of ``generated_at`` for ID building."""
        if not self.generated_at:
            return "00000000-0000"
        m = re.match(
            r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})", self.generated_at
        )
        if m:
            y, mo, d, h, mi = m.groups()
            return f"{y}{mo}{d}-{h}{mi}"
        return "00000000-0000"

    def to_pinecone_record(self) -> dict:
        """Convert to the Pinecone integrated-inference upsert_records shape.

        Pinecone's ``Index.upsert_records(namespace, records)`` expects a list of
        dicts with ``_id``, ``text``, plus arbitrary scalar metadata fields. List
        fields must be comma-joined per the §1 record-schema note (Pinecone
        metadata can't store heterogenous lists; comma-joined string is the
        documented compromise).
        """
        out = self.model_dump(exclude_none=True)
        # Lift `id` → `_id` (Pinecone convention)
        if "id" in out:
            out["_id"] = out.pop("id")
        # Comma-join list fields
        if "catalysts" in out and isinstance(out["catalysts"], list):
            out["catalysts"] = ", ".join(out["catalysts"])
        return out


# ---------------------------------------------------------------------------
# Module self-test (the slice 3a clean-venv gate)
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    # The slice 3a gate: prints the JSON schema without ImportError. Proves the
    # module is importable standalone (clean virtualenv with only pydantic).
    import json

    print(json.dumps(RecordMetadata.model_json_schema(), indent=2)[:1500])
    print(f"\nSCHEMA_VERSION = {SCHEMA_VERSION}")
    print(f"ReportType values: {sorted(t.value for t in ReportType)}")
    print(f"Signal values:     {sorted(s.value for s in Signal)}")
    print(f"Grade values:      {sorted(g.value for g in Grade)}")
    print(f"StrategyOutlook:   {sorted(o.value for o in StrategyOutlook)}")
    print(f"PositionBias:      {sorted(p.value for p in PositionBias)}")
    print(f"Allowed namespaces (slice 3a): {sorted(ALLOWED_NAMESPACES)}")
