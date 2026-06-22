#!/usr/bin/env python3
"""
test_build_sweep_payload.py — contract tests for build_sweep_payload.

No test framework is used (the repo has none); run directly:
    python3 scripts/test_build_sweep_payload.py
Exits non-zero on the first failed assertion.
"""
import build_sweep_payload as b

TS = "2026-06-20T13:17:13"


def _payload(mode, raw, run_id="options-20260620-1306-cb0e9c"):
    p, errs, warns = b.build_payload(mode, run_id, raw, timestamp=TS)
    return p, errs, warns


def test_to_overlay_mirrors_receiver():
    # PMCC must NOT collapse to COVERED_CALL (it's a diagonal); covered call still maps.
    assert b.to_overlay("Poor Man's Covered Call") == "CALL_DIAGONAL"
    assert b.to_overlay("PMCC (pending liquidity)") == "CALL_DIAGONAL"
    assert b.to_overlay("Covered Call (near-ATM)") == "COVERED_CALL"
    assert b.to_overlay("Collar") == "COLLAR"
    assert b.to_overlay("Protective Put") == "PROTECTIVE_PUT"
    assert b.to_overlay("Long Put") == "PROTECTIVE_PUT"
    assert b.to_overlay("Call Diagonal Spread") == "CALL_DIAGONAL"
    assert b.to_overlay("Bear Put Spread") == "BEAR_PUT_SPREAD"
    assert b.to_overlay("LEAP") == "LEAP"
    # No executable equivalent → None (ticker gets skipped, never shipped without an enum).
    assert b.to_overlay("Hold and Accumulate") is None
    assert b.to_overlay("Iron Condor") is None
    assert b.to_overlay("Cash-Secured Put") is None


def test_options_regression_2026_06_20():
    """The exact sweep that failed: every emitted change must carry a valid overlay,
    Hold-style postures must be skipped, and validation must pass."""
    postures = [
        {"ticker": "CLOV", "position_bias": "LONG", "strategy_outlook": "HEDGE", "recommended_strategy": "Collar"},
        {"ticker": "DIVO", "position_bias": "LONG", "strategy_outlook": "BULLISH", "recommended_strategy": "PMCC or Hold"},
        {"ticker": "IBIT", "position_bias": "LONG", "strategy_outlook": "INCOME", "recommended_strategy": "Covered Call"},
        {"ticker": "SPCE", "position_bias": "LONG", "strategy_outlook": "HEDGE", "recommended_strategy": "Protective Put"},
        {"ticker": "VDY", "position_bias": "LONG", "strategy_outlook": "INCOME", "recommended_strategy": "Covered Call (options illiquid/unavailable on TSX ETF)"},
        {"ticker": "XIC", "position_bias": "LONG", "strategy_outlook": "INCOME", "recommended_strategy": "PMCC (Poor Man's Covered Call — pending options liquidity verification)"},
        {"ticker": "XEQT", "position_bias": "LONG", "strategy_outlook": "BULLISH", "recommended_strategy": "Hold and Accumulate (insufficient shares for options)"},
        {"ticker": "YNVDA", "position_bias": "LONG", "strategy_outlook": "INCOME", "recommended_strategy": "Hold for Weekly Distributions"},
    ]
    p, errs, warns = _payload("options", {"postures": postures})
    assert errs == [], errs
    assert p is not None
    tickers = {c["ticker"] for c in p["signal_changes"]}
    assert tickers == {"US.CLOV", "US.DIVO", "US.IBIT", "US.SPCE", "CA.VDY", "CA.XIC"}, tickers
    for c in p["signal_changes"]:
        assert c["overlay"] in b.VALID_OVERLAYS, c
        assert set(c) == b.OPTIONS_CHANGE_KEYS, c
    overlays = {c["ticker"]: c["overlay"] for c in p["signal_changes"]}
    assert overlays["CA.XIC"] == "CALL_DIAGONAL"   # PMCC, not COVERED_CALL
    assert overlays["US.DIVO"] == "CALL_DIAGONAL"  # "PMCC or Hold"
    assert overlays["CA.VDY"] == "COVERED_CALL"
    # INCOME clears AutoTrader's 0.6 gate.
    assert overlays and all(c["points_delta"] == 6 for c in p["signal_changes"] if c["transition"][1] == "INCOME")
    assert any("skipped" in w for w in warns)  # XEQT + YNVDA skipped


def test_neutral_only_emits_empty_valid_payload():
    p, errs, warns = _payload("options", {"postures": [
        {"ticker": "ZAG", "position_bias": "LONG", "strategy_outlook": "NEUTRAL", "recommended_strategy": "Hold"},
    ]})
    assert errs == []
    assert p["signal_changes"] == []


def test_bad_run_id_fails_closed():
    p, errs, _ = _payload("options", {"postures": []}, run_id="PUT_OPTIONS_RUN_ID_HERE")
    assert p is None and "routine_id" in errs


def test_sweep_mode_no_overlay_plus_stops_catalysts():
    raw = {
        "rows": [
            {"ticker": "DIVO", "prior_signal": "HOLD", "new_signal": "BUY", "new_score": 71},
            {"ticker": "YNVDA", "prior_signal": "HOLD", "new_signal": "AVOID", "new_score": 22},
            {"ticker": "XEQT", "prior_signal": "HOLD", "new_signal": "HOLD", "new_score": 75},  # skipped
        ],
        "stops": [{"ticker": "SPCE", "stop_price": 1.80}],
        "catalysts": [{"ticker": "O/VDY", "event": "BoC", "date": "2026-07-15", "value": 64}],
    }
    p, errs, _ = b.build_payload("sweep", "routine-20260620-1105-5b0701", raw, timestamp=TS)
    assert errs == [], errs
    ch = {c["ticker"]: c for c in p["signal_changes"]}
    assert set(ch) == {"US.DIVO", "US.YNVDA"}            # HOLD skipped
    assert ch["US.DIVO"]["direction"] == "UP" and ch["US.DIVO"]["points_delta"] == 7   # round(71/10)
    assert ch["US.YNVDA"]["direction"] == "DOWN" and ch["US.YNVDA"]["points_delta"] == -10
    for c in p["signal_changes"]:
        assert "overlay" not in c                         # equity signals carry no overlay
    assert p["hard_stops"] == {"US.SPCE": 1.80}
    assert {c["ticker"] for c in p["catalysts"]} == {"US.O", "CA.VDY"}  # multi-symbol split + qualified


def test_sweep_emits_portfolio_targets():
    raw = {"rows": [
        {"ticker": "DIVO", "prior_signal": "HOLD", "new_signal": "BUY", "new_score": 71},
        {"ticker": "O", "prior_signal": "HOLD", "new_signal": "HOLD", "new_score": 55},
        {"ticker": "IAU", "prior_signal": "NEUTRAL", "new_signal": "NEUTRAL", "new_score": 41},
        {"ticker": "YNVDA", "prior_signal": "HOLD", "new_signal": "AVOID", "new_score": 22},   # exit -> excluded
        {"ticker": "SPCE", "prior_signal": "HOLD", "new_signal": "BUY"},                       # no score -> skipped+warned
    ]}
    p, errs, warns = b.build_payload("sweep", "routine-20260622-1455-abc123", raw, timestamp=TS)
    assert errs == [], errs
    tg = {t["symbol"]: t["score"] for t in p["portfolio_targets"]}
    assert tg == {"US.DIVO": 71.0, "US.O": 55.0, "US.IAU": 41.0}      # BUY+HOLD+NEUTRAL; AVOID + no-score excluded
    assert all(isinstance(v, float) for v in tg.values())
    assert any("target(s) skipped" in w for w in warns)               # SPCE reported


def test_sweep_targets_dedup_and_qualify():
    raw = {"rows": [
        {"ticker": "vdy", "new_signal": "BUY", "new_score": 60},      # CA. qualified, lowercased
        {"ticker": "US.AAPL", "new_signal": "HOLD", "new_score": 50},  # already qualified
        {"ticker": "AAPL", "new_signal": "BUY", "new_score": 90},      # dup of US.AAPL -> last wins
    ]}
    p, _, _ = b.build_payload("sweep", "routine-20260622-1455-abc123", raw, timestamp=TS)
    tg = {t["symbol"]: t["score"] for t in p["portfolio_targets"]}
    assert tg == {"CA.VDY": 60.0, "US.AAPL": 90.0}


def test_sweep_empty_when_no_scored_rows():
    raw = {"rows": [
        {"ticker": "YNVDA", "new_signal": "AVOID", "new_score": 22},   # exit
        {"ticker": "SPCE", "new_signal": "BUY"},                       # no score
        {"ticker": "ZAG", "new_signal": "HOLD", "new_score": 0},       # score <= 0
    ]}
    p, errs, _ = b.build_payload("sweep", "routine-20260622-1455-abc123", raw, timestamp=TS)
    assert errs == []
    assert p["portfolio_targets"] == []


def test_options_mode_has_no_portfolio_targets():
    p, errs, _ = _payload("options", {"postures": [
        {"ticker": "AAPL", "position_bias": "LONG", "strategy_outlook": "INCOME", "recommended_strategy": "Covered Call"},
    ]})
    assert errs == []
    assert "portfolio_targets" not in p


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print("PASS %s" % t.__name__)
    print("\nAll %d tests passed." % len(tests))


if __name__ == "__main__":
    main()
