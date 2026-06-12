# Testing Patterns

**Analysis Date:** 2026-06-08

## Test Framework & Tools

**Test Infrastructure:**
- **No formal test suite** — no pytest, unittest, or test framework configured
- **No linter** — no pylint, flake8, eslint, or Prettier configured
- **No build step** — no compilation, transpilation, or asset bundling
- **Manual testing only** — through direct invocation in Claude Code sessions

The codebase relies on:
1. **Runtime Pydantic validation** — schema contracts enforced at runtime
2. **Module self-tests** — `if __name__ == "__main__":` blocks in critical modules
3. **Gate scripts** — contract verification and schema validation gates
4. **Manual skill invocation** — testing commands directly in Claude Code
5. **Contract verification** — cross-file consistency checks during development

## Manual Testing Workflow

**Installation & Invocation:**
```bash
./install.sh                              # Install skills/agents/scripts to ~/.claude
# Then in a Claude Code session:
/trade analyze AAPL                       # Test full analysis flow
/trade quick AAPL                         # Test quick snapshot
/trade options AAPL                       # Test options strategy
/trade routine                            # Test portfolio sweep
```

This is the primary testing surface — every skill is a callable prompt that executes and produces observable output (`TRADE-*.md` files, terminal output, Slack posts, Drive uploads).

**Python Script Testing:**
```bash
# Module self-tests (require correct environment setup)
python3 scripts/trade_scoring.py          # Tests 6-band score→grade→signal mapping
python3 scripts/trade_schemas.py          # Prints JSON schema, verifies imports

# PDF generator demo mode
python3 scripts/generate_trade_pdf.py     # Generates TRADE-REPORT-sample.pdf (demo data)

# With real data
python3 scripts/generate_trade_pdf.py data.json TRADE-REPORT.pdf

# Pinecone memory operations (requires PINECONE_API_KEY)
python3 scripts/trade_memory.py init      # Create/verify index
python3 scripts/trade_memory.py ingest TRADE-ANALYSIS-AAPL.md
python3 scripts/trade_memory.py doctor    # Health check
```

**Proxy (Vercel) Testing:**
Local development:
```bash
python3 scripts/run_local_proxy.py        # Starts wsgiref server on http://localhost:8000
# Then POST to http://localhost:8000/upsert, /query, /list, /fetch, /delete with Bearer token
```

## Test File Organization

**No test files** — testing is done through direct skill invocation, not test suites.

**Module self-tests (if __name__ == "__main__"):**

Location: `scripts/trade_scoring.py`, `scripts/trade_schemas.py`

These are lightweight verification blocks that validate critical logic:
- `scripts/trade_scoring.py` — Tests 6-band boundary cases (score → grade → signal)
- `scripts/trade_schemas.py` — Prints JSON schema and verifies enum values

Run with:
```bash
python3 scripts/trade_scoring.py    # Should print "All 6 boundary cases pass."
python3 scripts/trade_schemas.py    # Should print schema and SCHEMA_VERSION
```

**Gate scripts (verification scripts):**
Not full tests, but contract-validation gates used in CI/deployment:
- `scripts/sync_proxy_schemas.sh` — Verifies `proxy/_lib/trade_schemas.py` matches `scripts/trade_schemas.py`
- Plan gates (D.17) — Verify schema-version consistency between docs and code
- Plan gates (D.19) — Smoke-test the proxy with curl requests

## Test Structure Patterns

**Module Self-Test Pattern (in __main__):**

From `scripts/trade_scoring.py`:
```python
if __name__ == "__main__":
    # Self-test: routing the 6 boundary scores produces the canonical labels.
    cases = [
        (85, "A+", "STRONG BUY"),
        (70, "A",  "BUY"),
        (55, "B",  "HOLD"),
        (40, "C",  "NEUTRAL"),
        (25, "D",  "CAUTION"),
        (0,  "F",  "AVOID"),
    ]
    failures = []
    for score, want_grade, want_signal in cases:
        got_grade = score_grade(score)
        got_signal = trade_signal(score)
        ok_g = got_grade == want_grade
        ok_s = got_signal == want_signal
        mark = "OK" if (ok_g and ok_s) else "FAIL"
        print(f"  score={score:3d}  grade={got_grade:<2}  signal={got_signal:<10}  [{mark}]")
        if not ok_g or not ok_s:
            failures.append(...)
    if failures:
        print("\nFAILED:")
        for f in failures:
            print(f"  - {f}")
        raise SystemExit(1)
    print("\nAll 6 boundary cases pass.")
```

**Key pattern:**
- Test critical boundary cases
- Print clear output showing each case result
- Collect failures in a list
- Exit with code 1 on failure, 0 on success
- Print summary at the end

**Schema Validation Pattern (Pydantic):**

From `scripts/trade_schemas.py`:
```python
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
```

**Key pattern:**
- Use `@field_validator` on fields requiring runtime checks
- Compare against enum values or allowlist
- Raise `ValueError` with descriptive message including what was valid
- Return the validated value

## Mocking

**Framework:** No mocking framework (no unittest.mock, pytest.monkeypatch, etc.)

**Why:** The codebase doesn't have automated tests, so there's no need for mocks. Integration testing happens through direct skill invocation in Claude Code.

**When manual mocking is needed (e.g., during skill development):**
- Use Claude Code's in-session WebSearch and WebFetch tools as the "real" implementation
- To test without hitting live APIs, modify a skill's hardcoded data in the prompt temporarily
- The Pinecone client in `scripts/trade_memory.py` checks for env vars; set/unset them to control which backend is used

## Fixtures and Factories

**No test fixtures** — no test data files, factories, or builders.

**Test data approach:**
- Manual (hard-code in skill) for single-use scenarios
- Real data from WebSearch (preferred for realistic testing)
- Demo mode for PDF generator: `python3 scripts/generate_trade_pdf.py` without args uses hardcoded sample data

**Demo data location:** `scripts/generate_trade_pdf.py` lines 200–250 (DEMO_DATA dict)

## Coverage

**Requirements:** No coverage enforcement (no threshold, no CI gates)

**View coverage:** Not applicable — no test suite to measure

**Code review approach:** 
- Manual inspection of skill logic before pushing
- Pydantic models catch schema errors
- Self-tests validate critical boundaries
- Gate scripts verify cross-file contracts

## Test Types

**Unit Tests:** Not used

**Integration Tests:** Skills are the "integration tests" — each skill is a self-contained prompt that exercises multiple downstream systems (WebSearch, WebFetch, Pinecone, etc.). Testing happens by running `/trade analyze AAPL` and inspecting the output.

**E2E Tests:** Not formalized, but the full `/trade routine` sweep is closest to an E2E test — it exercises holdings lookup, tiering, per-ticker analysis, escalation, digest writing, and Slack posting.

**Manual E2E Flow:**
```bash
/trade holdings                           # Reads portfolio from Drive
/trade routine                            # Full sweep (uses analyze/quick/escalate)
/trade recall "bull case"                 # Semantic search over past reports
/trade report-pdf                         # Generates PDF from past analyses
```

## Common Testing Patterns in This Codebase

**Validation at the boundary (Pydantic models):**

The proxy (`proxy/_lib/validate.py`) uses Pydantic to validate all incoming payloads:
```python
class UpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")  # Reject unknown fields
    namespace: str
    records: List[dict] = Field(min_length=1, max_length=100)
    
    @field_validator("records")
    @classmethod
    def _validate_records(cls, records):
        for i, rec in enumerate(records):
            normalized = dict(rec)
            if "_id" in normalized and "id" not in normalized:
                normalized["id"] = normalized.pop("_id")
            try:
                RecordMetadata(**normalized)  # Re-validate via canonical model
            except Exception as e:
                raise ValueError(f"records[{i}]: schema violation — {e}")
        return records
```

**Key pattern:**
- Models enforce `extra="forbid"` to catch producer/consumer drift
- Custom validators re-validate complex fields (lists of records)
- Error messages are descriptive and include context (which record index, which field)

**Enum validation (ensuring exactly 6 signal labels):**

From `scripts/trade_schemas.py`:
```python
class Signal(str, Enum):
    """Composite trade signal. Exactly 6 values. UPPERCASE in metadata storage."""
    STRONG_BUY = "STRONG BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    NEUTRAL = "NEUTRAL"
    CAUTION = "CAUTION"
    AVOID = "AVOID"
```

Verified by self-test:
```python
print(f"Signal values: {sorted(s.value for s in Signal)}")  # Prints all 6
```

**HTTP error handling in the proxy (status codes):**

From `proxy/app.py`:
- 401 Unauthorized: bearer token validation failed
- 400 Bad Request: payload schema violation
- 404 Not Found: unknown endpoint
- 405 Method Not Allowed: non-POST request
- 429 Too Many Requests: rate limit exceeded
- 500 Internal Server Error: Pinecone unavailable or other runtime issue

Tested by:
1. Gate script (D.19) makes curl requests to each endpoint with invalid/missing auth
2. Manual testing via `scripts/run_local_proxy.py` + Postman collection (`proxy/postman/`)

## Contract Verification Gates

**Schema version consistency (D.17 gate):**
- Verifies `SCHEMA_VERSION` in `scripts/trade_schemas.py` matches the Pydantic model
- Verifies `proxy/_lib/trade_schemas.py` is byte-identical to `scripts/trade_schemas.py`
- Run: `bash scripts/sync_proxy_schemas.sh` to keep them in sync

**Scoring weight consistency (manual contract audit):**
- Weights documented in 5 places (listed in CONVENTIONS.md)
- No automated gate, but any change to one must propagate to all others
- Verified during code review

**Signal label exactness (boundary test):**
- `scripts/trade_scoring.py` self-test ensures 6 boundaries produce 6 distinct grades/signals
- Run `python3 scripts/trade_scoring.py` to verify

**Pinecone schema availability (D.3a gate):**
- Verifies `scripts/trade_schemas.py` imports cleanly in a virtualenv with only Pydantic installed
- Ensures the module can be vendored without transitive Pinecone SDK dependencies
- Run: `python3 scripts/trade_schemas.py` (should not ImportError)

## No CI/CD Test Suite

**Why no pytest?**
1. Skills are prompts, not code modules — they're invoked by Claude Code, not by a test runner
2. Python scripts are utility/integration tools, not libraries with unit-testable logic
3. Quality is ensured by manual skill invocation + Pydantic validation at runtime
4. Proxy has no local test suite; gate scripts (D.19) smoke-test via HTTP

**Quality gates instead:**
- Pydantic models validate schemas at runtime
- Module self-tests (`if __name__ == "__main__":`) verify critical logic
- Gate scripts verify contracts (schema version, scoring weights, proxy sync)
- Human code review before merging
- Live testing in Claude Code sessions

## Testing Gotchas & Known Limits

**PDF generator demo mode:**
- `python3 scripts/generate_trade_pdf.py` with no arguments runs demo mode, ignoring `/tmp/trade_report_data.json`
- To render real data: `python3 scripts/generate_trade_pdf.py /path/to/data.json output.pdf`
- Common mistake: writing data to `/tmp/trade_report_data.json`, then forgetting to pass the path as an argument

**Pinecone availability degradation:**
- If `PINECONE_API_KEY` is unset or the proxy is unreachable, `trade_memory.py` commands gracefully degrade
- `/trade routine` still runs (emits "memory unavailable" note); `/trade recall` returns empty results
- Test with: `unset PINECONE_API_KEY && /trade routine`

**Scoring weight drift:**
- The 6-band table is defined in 5 different places
- A weight change in one place but not others causes silent inconsistency (no error, just wrong results)
- Mitigation: always update all 5 files together, then run a manual sanity check

**Bearer token in logs:**
- The proxy intentionally NEVER logs the bearer token itself, only "auth ok" / "auth failed"
- Test: tail the logs while making a request with wrong token — should NOT see the token value

## Manual Testing Checklist

When developing a new skill or modifying critical logic, test these scenarios:

**Skill development:**
- [ ] Edit the `.md` file
- [ ] Run `./install.sh` to copy to `~/.claude/`
- [ ] Invoke the command in Claude Code (e.g., `/trade analyze AAPL`)
- [ ] Verify output file is created with correct name (`TRADE-ANALYSIS-AAPL.md`)
- [ ] Spot-check for specific numbers (no fabricated data)
- [ ] Verify bull + bear cases are both present
- [ ] Check disclaimer is present and correct
- [ ] Look for any unintended formatting or broken tables

**Python script modification:**
- [ ] Run any self-tests: `python3 scripts/trade_scoring.py`
- [ ] Test the main use case: `python3 scripts/trade_memory.py doctor`
- [ ] Check error messages are clear for invalid inputs

**Schema changes (trade_schemas.py):**
- [ ] Run the module: `python3 scripts/trade_schemas.py` (should not error)
- [ ] Run the scoring self-test: `python3 scripts/trade_scoring.py`
- [ ] Run `bash scripts/sync_proxy_schemas.sh` to keep proxy copy in sync
- [ ] If you changed `SCHEMA_VERSION`, update it in all places (run grep to find them)

**Cross-file contract changes (scoring weights, signal labels):**
- [ ] Update all 5 locations simultaneously
- [ ] Run `python3 scripts/trade_scoring.py` to verify boundary cases
- [ ] Manually verify `trade/SKILL.md`, `README.md`, `skills/trade-analyze/SKILL.md`, and one agent file match
- [ ] Run a full `/trade analyze AAPL` and check the composite score calculation

---

*Testing analysis: 2026-06-08*
