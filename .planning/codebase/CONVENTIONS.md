# Coding Conventions

**Analysis Date:** 2026-06-08

## Naming Patterns

**Files:**
- Markdown prompt files: `SKILL.md` (skills and orchestrator), agent files without suffix (e.g., `trade-technical.md`)
- Output Markdown reports: `TRADE-<TYPE>-<TICKER>.md` (e.g., `TRADE-ANALYSIS-AAPL.md`, `TRADE-QUICK-NVDA.md`)
- Python scripts: `snake_case.py` with shebang `#!/usr/bin/env python3`
- Bash scripts: lowercase with `.sh` extension (e.g., `install.sh`, `uninstall.sh`)

**Functions & Classes (Python):**
- Classes: `PascalCase` (e.g., `RecordMetadata`, `AuthError`, `ValidationError`)
- Functions: `snake_case` (e.g., `check_bearer`, `score_grade`, `upsert_op`)
- Constants: `UPPERCASE` (e.g., `SCHEMA_VERSION`, `ALLOWED_NAMESPACES`, `COLORS`)
- Private/internal functions: prefix with `_` (e.g., `_import_sibling`, `_ticker_format`)

**Variables:**
- Module-level: `UPPERCASE` (constants) or `snake_case` (module state)
- Local: `snake_case` (e.g., `expected`, `presented`, `idx`)
- Boolean flags: prefix with `is_` or `has_` (e.g., `is_allowed_namespace()`, `has_values`)

**Types (Python):**
- Type hints on all function signatures: parameters and return types
- Use `Optional[T]` from `typing` for nullable values
- Use `List[T]`, `dict`, `str`, `int`, `float`, `bool` as appropriate
- Pydantic field annotations: `Field(default=None, ge=0, le=100)` for validation constraints

## Code Style

**Formatting:**
- No automated formatter configured (no Black, no Prettier)
- Python: follow PEP 8 style guide
- Markdown: use standard Markdown syntax with explicit headers (##, ###)
- Indentation: 4 spaces (Python), 2 spaces (Markdown lists/tables when needed)
- Line length: avoid extremely long lines; wrap at ~120 characters where reasonable

**Linting:**
- No linter configured (no pylint, no flake8, no eslint)
- Code quality relies on manual review and Pydantic validation at runtime
- Cross-file contracts verified by gate scripts (not a pre-commit hook)

## Import Organization

**Python order:**
1. Standard library imports (`sys`, `os`, `json`, `datetime`, `pathlib`, etc.)
2. Third-party imports (`pydantic`, `reportlab`, etc.)
3. Local sibling imports (via `importlib.util.spec_from_file_location` or relative)
4. Special note: Lazy-loaded imports for optional dependencies like Pinecone SDK wrapped in try/except

**Path aliases:**
- Sibling module resolution: `_import_sibling()` in `trade_memory.py` and `generate_trade_pdf.py`
- Pattern: `spec = importlib.util.spec_from_file_location(name, _HERE / f"{name}.py")`
- Allows scripts to work from repo root (`scripts/`) or after install (`~/.claude/skills/trade/scripts/`)
- No sys.path manipulation for production code; only in local dev contexts

**Example from `scripts/trade_memory.py`:**
```python
_HERE = pathlib.Path(__file__).resolve().parent

def _import_sibling(name: str):
    spec = importlib.util.spec_from_file_location(name, _HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

trade_schemas = _import_sibling("trade_schemas")
trade_scoring = _import_sibling("trade_scoring")
```

## Markdown Prompt Conventions (Skills & Agents)

**YAML Frontmatter (required):**
Every skill and agent file MUST have a frontmatter block:
```yaml
---
name: <skill-name>
description: <one-sentence description>
---
```

The `name` field is how Claude Code routes commands. The `description` is shown in skill listings.

**Agent File Header (agents/*.md only):**
Agent files must preserve a specific header structure after frontmatter:
```markdown
---
name: trade-technical
description: Technical analysis specialist...
---

# Technical Analysis Agent

**Weight:** 25% of composite Trade Score
**Output:** technical_score (0-100), key_levels, trend_direction, pattern_detected, signal

**DISCLAIMER: For educational/research purposes only. Not financial advice.**
```

Required lines:
- `# [Name] Agent` — section title
- `**Weight:**` — percentage of composite score (25%, 20%, 15%, etc.)
- `**Output:**` — list of fields this agent produces
- `**DISCLAIMER:**` — must state "For educational/research purposes only. Not financial advice."

**Scoring weights (CRITICAL CROSS-FILE CONTRACT):**
The weights are duplicated across multiple files and MUST be kept in sync:
- `trade/SKILL.md` lines 48-56 (Technical 25% / Fundamental 25% / Sentiment 20% / Risk 15% / Thesis 15%)
- `skills/trade-analyze/SKILL.md` (same weights in agent mandates)
- Each `agents/trade-*.md` file (the **Weight:** header)
- `README.md` "Scoring Methodology" section
- `plan/portfolio-routine-and-vector-memory.md` §1 field-contract table

**Score→Grade→Signal table (CRITICAL CROSS-FILE CONTRACT):**
The 6-band mapping must be consistent everywhere:
- 85-100: A+ / STRONG BUY
- 70-84: A / BUY
- 55-69: B / HOLD
- 40-54: C / NEUTRAL
- 25-39: D / CAUTION
- 0-24: F / AVOID

Used in: `trade/SKILL.md` lines 57-64, `README.md`, `scripts/trade_scoring.py`, `scripts/trade_schemas.py`, `agents/*.md` interpretation tables.

**Output format requirements:**
All skill outputs (written Markdown files) must:
1. **Cite specific numbers** — never fabricate or say "Data not available" unless genuinely unavailable
2. **Provide bull + bear cases** — always show both sides of the thesis
3. **Include timestamp** — analysis date and time (generated_at ISO-8601 with timezone)
4. **End with disclaimer** — "For educational and research purposes only. Not financial advice."
5. **Use structured headers** — ## (main sections), ### (subsections), #### (details)
6. **Cite data sources** — when pulling specific figures, note where they came from (e.g., "Yahoo Finance", "SEC", "Seeking Alpha")

**Example structure:**
```markdown
# TRADE ANALYSIS — AAPL

**Generated:** 2026-06-08 14:32:00 UTC

## Executive Summary

TRADE SCORE: 74/100 (Grade: A) — BUY

## Bull Case

[Specific numbers, catalysts, timeline]

## Bear Case

[Specific risks, headwinds, downside scenarios]

## Technical Analysis

[...]

---

**DISCLAIMER:** This is for educational and research purposes only. It is NOT financial advice...
```

## Python Code Conventions

**Docstrings:**
- Module level: detailed explanation of purpose, usage, and dependencies (see `scripts/trade_schemas.py`, `scripts/trade_memory.py`)
- Class level: what the class represents and its role in the system
- Function level: one-line summary, then parameter descriptions, return type, exception handling notes
- Format: Google-style or brief inline comments for simple functions

**Example from `proxy/_lib/auth.py`:**
```python
"""Constant-time bearer-token check for the AI Trading Analyst proxy.

Layer 2 of the 5-layer auth model...
"""

def check_bearer(authorization_header: Optional[str]) -> None:
    """Validate an Authorization header. Raises ``AuthError`` on any failure.

    Failure modes (all map to HTTP 401...):
    - Missing header
    - Header doesn't start with ``Bearer ``
    - Token doesn't match (constant-time compared)
    - Deployment has no ``PROXY_AUTH_TOKEN`` configured
    """
```

**Type Hints:**
- All function signatures must include parameter and return type annotations
- Use `Optional[T]` for nullable values (from `typing` module)
- Use `List[T]`, `dict`, `str`, `int`, etc. for container types
- Pydantic models: annotate with `Field()` for constraints

**Exception Handling:**
- Define custom exception classes inheriting from `Exception`
- Include descriptive `__init__` methods with reason/details
- Catch specific exception types, not bare `Exception`
- Log meaningful context (but never log secrets like auth tokens)

**Example from `proxy/_lib/auth.py`:**
```python
class AuthError(Exception):
    """Raised when a request fails bearer validation. Maps to HTTP 401."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason
```

**Pydantic Models:**
- Use `BaseModel` as base class
- Set `model_config = ConfigDict(extra="forbid")` to prevent unknown fields
- Use `Field()` for validation constraints: `ge=0, le=100` (numeric bounds), `min_length=1`, `max_length=100`
- Use `@field_validator` decorator for custom validation logic
- Return annotated return values or raise `ValueError` with clear error messages
- Call `.model_dump(exclude_none=True)` when serializing

**Example from `scripts/trade_schemas.py`:**
```python
class RecordMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    schema_version: int = SCHEMA_VERSION
    ticker: str
    composite_score: Optional[int] = Field(default=None, ge=0, le=100)
    
    @field_validator("ticker")
    @classmethod
    def _ticker_format(cls, v: str) -> str:
        if not TICKER_PATTERN.match(v):
            raise ValueError(f"ticker must match {TICKER_PATTERN.pattern}; got {v!r}")
        return v
```

**Comments & Markdown sections:**
- Use markdown-style comment headers for section breaks (##, ###, etc.)
- Group related code under labeled sections in longer files
- Explain WHY, not WHAT (code explains what; comments explain reasoning)

**Example from `scripts/trade_memory.py`:**
```python
# ---------------------------------------------------------------------------
# Sibling module resolution — works from any CWD or install location.
# Pattern documented in plan §"import resolution".
# ---------------------------------------------------------------------------
_HERE = pathlib.Path(__file__).resolve().parent
```

**Module self-tests:**
- Include a self-test block for critical modules: `if __name__ == "__main__":`
- Test the module's primary logic and output format
- `scripts/trade_scoring.py` tests the 6-band boundary cases
- `scripts/trade_schemas.py` prints the JSON schema for contract verification
- Exit with code 0 (success) or 1 (failure)

**Example from `scripts/trade_scoring.py`:**
```python
if __name__ == "__main__":
    # Self-test: routing the 6 boundary scores produces the canonical labels.
    cases = [
        (85, "A+", "STRONG BUY"),
        (70, "A",  "BUY"),
        # ... etc
    ]
    for score, want_grade, want_signal in cases:
        got_grade = score_grade(score)
        got_signal = trade_signal(score)
        # ... validate and report
```

## Cross-File Contracts (The Easy Things to Break)

**Scoring weights are duplicated and must stay in sync:**
- Change one place → change all 4:
  1. `trade/SKILL.md` command reference table
  2. `skills/trade-analyze/SKILL.md` agent mandate sections
  3. Individual `agents/trade-*.md` **Weight:** headers
  4. `README.md` "Scoring Methodology" table
  5. `plan/portfolio-routine-and-vector-memory.md` if referenced

**Risk score is inverted:**
- Higher risk_score (0-100) means SAFER (less risk)
- This is documented in `scripts/trade_schemas.py` line 162: "INVERTED — higher = safer"
- Must be consistent in agents/trade-risk.md and the composite formula

**Signal labels must be UPPERCASE in metadata:**
- Pydantic validation enforces this: `Signal(str, Enum)` with values "STRONG BUY", "BUY", "HOLD", "NEUTRAL", "CAUTION", "AVOID"
- Prose documents may use mixed case ("Strong Buy") for readability, but storage always uses UPPERCASE

**Grade must be single-letter only:**
- No B+, C+, C-, D+, etc. (M4 cleanup rule)
- Exactly 6 values: A+, A, B, C, D, F
- Enforced in `scripts/trade_schemas.py` line 243

**Pinecone record schema is a public contract:**
- Single source of truth: `scripts/trade_schemas.py`
- Mirrored in `proxy/_lib/trade_schemas.py` (synced by `bash scripts/sync_proxy_schemas.sh`)
- Consumers (trading-chatbot, recall skill, etc.) depend on field names and types
- Additive changes are safe (new optional fields, new enum values)
- Breaking changes (field rename, type change, enum value removal) require SCHEMA_VERSION bump
- After editing `scripts/trade_schemas.py`, run `bash scripts/sync_proxy_schemas.sh` to update the proxy copy

## Bash Script Conventions

**Header:**
- Start with `#!/bin/bash`
- Set `set -e` to exit on first error
- Include descriptive comment header

**Colors & output:**
- Use color variables for readability: `RED`, `GREEN`, `YELLOW`, `BLUE`, `CYAN`, `NC` (no color)
- Format: `echo -e "${GREEN}✓${NC} Message"`
- Progress messages: use check marks (✓), ✗, ⚠ for visual clarity

**Error handling:**
- Check prerequisites before main work
- Use descriptive error messages that guide the user to fix the issue
- Exit with meaningful codes: 0 (success), 1 (error), 2 (missing deps)

**Example from `install.sh`:**
```bash
#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}Installing...${NC}"
mkdir -p "$SKILLS_DIR/trade/scripts"
echo -e "  ${GREEN}✓${NC} Created directory"
```

## Error Handling

**Patterns (Python):**
- Use specific exception types, not bare `Exception`
- Include context in error messages (what was invalid, what was expected)
- For validation errors, include hints about valid options

**Pattern from `proxy/_lib/validate.py`:**
```python
def check_namespace(namespace: Optional[str]) -> str:
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
```

**Patterns (Markdown prompts):**
- Always state assumptions clearly
- If data is unavailable, explicitly say so instead of fabricating
- Provide fallback guidance (e.g., "Run `/trade analyze <ticker>` for the full analysis")

## Logging

**Framework:** No centralized logging framework. Use:
- `print()` for user-facing output
- `sys.stderr.write()` for diagnostic/error logs (in Python scripts)
- Bash `echo` for installation/setup progress

**Patterns:**
- Log authentication results: "auth ok" / "auth failed" (never log the token itself)
- Log operational milestones: "Created directory", "Upserted 5 records"
- Diagnostic format: structured, timestamp when relevant

**Example from `proxy/app.py`:**
```python
sys.stderr.write(f"[auth] {path} {_client_ip(environ)} 401: {e.reason}\n")
```

## Comments

**When to comment:**
- Complex logic that isn't obvious from variable names and function calls
- Workarounds and tradeoffs (with the date and rationale)
- References to external specifications or plans (e.g., "See plan/§1 for the record schema")
- Warnings about invariants or side effects

**JSDoc/TSDoc:** Not used (Markdown prompts, Python scripts, no TypeScript)

---

*Convention analysis: 2026-06-08*
