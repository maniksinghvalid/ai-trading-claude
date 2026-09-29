#!/usr/bin/env python3
"""
test_trade_quote.py — parse tests for trade_quote (no network).

    python3 scripts/test_trade_quote.py
"""
import trade_quote as q

OK = {"chart": {"result": [{"meta": {
    "symbol": "XIC.TO", "currency": "CAD", "regularMarketPrice": 56.44,
    "chartPreviousClose": 56.0, "fiftyTwoWeekHigh": 59.29, "fiftyTwoWeekLow": 47.17,
    "regularMarketTime": 1790698877}}], "error": None}}

ERR = {"chart": {"result": None, "error": {"code": "Not Found",
       "description": "No data found, symbol may be delisted"}}}


def test_parse_ok():
    r = q.parse_chart(OK)
    assert r["price"] == 56.44 and r["currency"] == "CAD"
    assert r["change_pct"] == 0.79
    assert r["high_52w"] == 59.29 and r["low_52w"] == 47.17
    assert r["as_of"].startswith("2026-") and r["as_of"].endswith("+00:00")


def test_parse_error_payload():
    try:
        q.parse_chart(ERR)
    except ValueError as e:
        assert "delisted" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_parse_missing_price():
    try:
        q.parse_chart({"chart": {"result": [{"meta": {}}]}})
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def main():
    tests = [test_parse_ok, test_parse_error_payload, test_parse_missing_price]
    for t in tests:
        t()
        print("PASS %s" % t.__name__)
    print("\nAll %d tests passed." % len(tests))


if __name__ == "__main__":
    main()
