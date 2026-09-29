#!/usr/bin/env python3
"""
trade_quote.py — authoritative price quotes so skills never have the model
transcribe a price from web-search snippets.

    python3 trade_quote.py SYM [SYM...]

Prints one JSON object keyed by symbol:
    {"CLOV": {"price": 4.28, "currency": "USD", "prev_close": ..., "change_pct": ...,
              "high_52w": ..., "low_52w": ..., "as_of": "<ISO-8601 UTC>", "source": "yahoo"},
     "BAD":  {"error": "..."}}
Canadian listings need the exchange suffix (XIC.TO). Exits 1 only when every
symbol failed. Stdlib only; keyless public endpoint, no brokerage.
"""
import datetime
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

URL = "https://query1.finance.yahoo.com/v8/finance/chart/%s?range=1d&interval=1d"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def parse_chart(payload: dict) -> dict:
    """Yahoo v8 chart JSON → quote dict. Raises ValueError on an error payload."""
    chart = payload.get("chart") or {}
    if chart.get("error"):
        raise ValueError(chart["error"].get("description") or str(chart["error"]))
    results = chart.get("result") or []
    if not results:
        raise ValueError("no result")
    m = results[0].get("meta") or {}
    price = m.get("regularMarketPrice")
    if price is None:
        raise ValueError("no regularMarketPrice")
    prev = m.get("chartPreviousClose") or m.get("previousClose")
    ts = m.get("regularMarketTime")
    return {
        "price": price,
        "currency": m.get("currency"),
        "prev_close": prev,
        "change_pct": round((price - prev) / prev * 100, 2) if prev else None,
        "high_52w": m.get("fiftyTwoWeekHigh"),
        "low_52w": m.get("fiftyTwoWeekLow"),
        "as_of": datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat() if ts else None,
        "source": "yahoo",
    }


def fetch(sym: str) -> dict:
    req = urllib.request.Request(URL % urllib.parse.quote(sym), headers={"User-Agent": UA})
    for attempt in (0, 1):
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return parse_chart(json.load(r))
        except urllib.error.HTTPError as e:
            if e.code == 404:  # Yahoo returns 404 + error JSON for unknown symbols
                try:
                    return parse_chart(json.load(e))
                except ValueError as ve:
                    return {"error": str(ve)}
                except Exception:
                    return {"error": "HTTP 404"}
            if attempt == 0 and (e.code == 429 or e.code >= 500):
                time.sleep(2)
                continue
            return {"error": "HTTP %d" % e.code}
        except Exception as e:  # network, timeout, bad JSON, ValueError from parse
            if attempt == 0 and not isinstance(e, ValueError):
                time.sleep(2)
                continue
            return {"error": "%s: %s" % (type(e).__name__, e)}


def main(argv):
    syms = [s.strip().upper() for s in argv if s.strip()]
    if not syms:
        print(__doc__, file=sys.stderr)
        return 2
    out = {s: fetch(s) for s in syms}
    print(json.dumps(out, indent=2))
    return 1 if all("error" in q for q in out.values()) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
