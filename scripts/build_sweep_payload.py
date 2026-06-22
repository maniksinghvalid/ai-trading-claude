#!/usr/bin/env python3
"""
build_sweep_payload.py — single source of truth for the AutoTrader sweep payload.

The cloud routines POST a RoutineSignalPayload to the AutoTrader paper-trade
webhook (`/webhook/sweep`). Historically the deterministic builder was duplicated
inline in THREE places that drifted independently:
  - `skills/trade-routine/SKILL.md` Step W,
  - the `trade-options-sweep` routine prompt (RemoteTrigger config),
  - the `trade-routine-daily-portfolio-sweep` routine prompt (RemoteTrigger config).
One copy fell behind and emitted options changes with no `overlay` enum, which the
receiver silently dropped. This module is that builder, committed once, installed by
`install.sh` to `~/.claude/skills/trade/scripts/`, and called by every Step W so the
contract can no longer drift between copies.

Two modes, mirroring the two sweep types:

  options  — options-posture overlays. Input `{"postures": [...]}`, each
             {ticker, position_bias, strategy_outlook, recommended_strategy}.
             Emits changes carrying an `overlay` enum (HEDGE/INCOME/BULLISH/BEARISH
             → direction+points; recommended_strategy → overlay via to_overlay()).
  sweep    — directional equity signals. Input `{"rows": [...], "stops": [...],
             "catalysts": [...]}`. Emits changes WITHOUT overlay (these are equity
             signals, not options instructions), plus hard_stops and catalysts.

Contract notes (keep in lockstep with AutoTrader `autotrader/signals/`):
  - `overlay` MUST be one of domain.OverlayType; the six in VALID_OVERLAYS. A change
    flagged overlay-intended (driver ends in "(options overlay)") but missing a valid
    enum is DROPPED by the receiver's normalize.py. So options changes ALWAYS carry it.
  - to_overlay() MUST mirror coerce.derive_overlay(): PMCC / "Poor Man's Covered Call"
    → CALL_DIAGONAL (NOT COVERED_CALL — a PMCC is a long-LEAP + short-call diagonal and
    COVERED_CALL needs 100 held shares → SKIP_NO_UNDERLYING).
  - INCOME → points_delta 6 (confidence 0.6) so income/covered-call overlays clear
    AutoTrader's 0.6 confidence gate; below that they are accepted then dropped.

On validation failure the payload is NOT written (caller's webhook step then skips),
a `[warn] ...` line is printed, and the process exits 0 — never fatal to the sweep.

CLI:
  python3 build_sweep_payload.py options --run-id options-... --in postures.json
  python3 build_sweep_payload.py sweep   --run-id routine-... --in inputs.json
  # default --out /tmp/sweep_payload.json; reads stdin when --in omitted.

Stdlib only (no pydantic, no project sys.path) so it runs in a clean cloud sandbox.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Canadian (TSX) ETFs → CA. prefix; everything else → US. prefix.
CA_TICKERS = {"VDY", "XEQT", "XIC", "ZAG"}

# Options posture → (direction, points_delta). NEUTRAL/other → skipped.
OUTLOOK_MAP = {
    "BULLISH": ("UP", 7),
    "BEARISH": ("DOWN", -7),
    "HEDGE": ("DOWN", -6),
    "INCOME": ("UP", 6),
}

# The ONLY overlays AutoTrader can execute (domain.OverlayType). Anything else is
# rejected/dropped by the receiver, so every emitted options change must carry one.
VALID_OVERLAYS = {
    "COVERED_CALL", "PROTECTIVE_PUT", "COLLAR",
    "CALL_DIAGONAL", "BEAR_PUT_SPREAD", "LEAP",
}

# Directional equity signal label classes (sweep mode), mirrors routine_adapter.
BUY_LABELS = {"BUY", "STRONG BUY"}
SELL_LABELS = {"CAUTION", "AVOID", "SELL"}
EXIT_POINTS = -10  # exits use confidence 1.0 so they always clear the gate

OPTIONS_CHANGE_KEYS = {"ticker", "direction", "transition", "points_delta", "driver", "overlay"}
SWEEP_CHANGE_KEYS = {"ticker", "direction", "transition", "points_delta", "driver"}


def qualify(ticker: Any) -> str:
    """Bare 'AAPL' → 'US.AAPL'; TSX names → 'CA.<t>'; already-qualified passes through."""
    t = str(ticker).strip().upper()
    if "." in t:
        return t
    return ("CA." if t in CA_TICKERS else "US.") + t


def to_overlay(strategy: Any) -> Optional[str]:
    """Map a recommended-strategy string to a VALID_OVERLAYS value, or None when
    AutoTrader has no executable equivalent. MUST mirror coerce.derive_overlay().

    Order matters: PMCC / diagonal are tested BEFORE the covered-call substring because
    "Poor Man's Covered Call" contains "COVERED CALL" but is a long-LEAP + short-call
    diagonal, so it must map to CALL_DIAGONAL, not COVERED_CALL.
    """
    s = str(strategy).upper().replace("-", " ")
    if "PMCC" in s or "POOR MAN" in s:
        return "CALL_DIAGONAL"
    if "DIAGONAL" in s:
        return "CALL_DIAGONAL"
    if "COVERED CALL" in s:
        return "COVERED_CALL"
    if "COLLAR" in s:
        return "COLLAR"
    if "BEAR PUT" in s:
        return "BEAR_PUT_SPREAD"
    if "PROTECTIVE PUT" in s or "MARRIED PUT" in s or "LONG PUT" in s:
        return "PROTECTIVE_PUT"
    if "LEAP" in s or "LONG CALL" in s:
        return "LEAP"
    return None  # Iron Condor, Cash-Secured Put, Bull Call Spread, Hold/no-option → skip


def _clamp(n: int) -> int:
    return max(0, min(10, n))


def build_options_changes(postures: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Map options postures to overlay-bearing signal changes. Returns (changes, skipped)."""
    changes: List[Dict[str, Any]] = []
    skipped: List[str] = []
    for p in postures:
        outlook = str(p.get("strategy_outlook", "")).strip().upper()
        if outlook not in OUTLOOK_MAP:
            continue  # NEUTRAL / unknown → not actionable
        rec = str(p.get("recommended_strategy", ""))
        overlay = to_overlay(rec)
        if overlay is None:
            skipped.append("%s=%s" % (p.get("ticker"), rec))  # no executable overlay → skip
            continue
        direction, pts = OUTLOOK_MAP[outlook]
        changes.append({
            "ticker": qualify(p.get("ticker")),
            "direction": direction,
            "transition": [str(p.get("position_bias", "")), str(p.get("strategy_outlook", ""))],
            "points_delta": int(pts),
            "driver": rec + " (options overlay)",
            "overlay": overlay,
        })
    return changes, skipped


def build_sweep_changes(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map directional ticker-sweep rows (BUY/SELL labels) to equity signal changes."""
    changes: List[Dict[str, Any]] = []
    for r in rows:
        label = str(r.get("new_signal", "")).strip().upper()
        score = r.get("new_score")
        if label in BUY_LABELS:
            direction, pts = "UP", _clamp(round(float(score or 0) / 10))  # conviction scales with score
        elif label in SELL_LABELS:
            direction, pts = "DOWN", EXIT_POINTS
        else:
            continue  # HOLD / NEUTRAL / unknown → skip
        changes.append({
            "ticker": qualify(r.get("ticker")),
            "direction": direction,
            "transition": [str(r.get("prior_signal", "")), str(r.get("new_signal", ""))],
            "points_delta": int(pts),
            "driver": "ticker sweep (score %s)" % score,
        })
    return changes


def build_portfolio_targets(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Map ticker-sweep rows to renormalizable weight targets for the rebalancer.
    Full-book: every non-exit holding carrying a finite, positive composite score
    becomes a target (BUY / STRONG BUY / HOLD / NEUTRAL alike). Exit labels
    (CAUTION / AVOID / SELL) are excluded — the DOWN signal-change path handles
    those. Rows without a usable score (e.g. quick-tier, which emits no score) are
    skipped and reported. Dedup by qualified symbol, last row wins. The receiver
    renormalizes raw scores into weights, so no scaling/clamping happens here.
    Returns (targets, skipped_tickers)."""
    by_symbol: Dict[str, float] = {}
    skipped: List[str] = []
    for r in rows:
        label = str(r.get("new_signal", "")).strip().upper()
        if label in SELL_LABELS:
            continue  # exit — never a target
        try:
            score = float(r.get("new_score"))
        except (TypeError, ValueError):
            skipped.append(str(r.get("ticker")))
            continue
        if not math.isfinite(score) or score <= 0:
            skipped.append(str(r.get("ticker")))
            continue
        by_symbol[qualify(r.get("ticker"))] = score  # last row wins on duplicate
    targets = [{"symbol": s, "score": v} for s, v in by_symbol.items()]
    return targets, skipped


def build_hard_stops(stops: List[Dict[str, Any]]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for s in stops:
        out[qualify(s.get("ticker"))] = float(s.get("stop_price"))
    return out


def build_catalysts(catalysts_in: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for c in catalysts_in:
        for tk in str(c.get("ticker", "")).replace("/", " ").split():  # split multi-symbol X/Y/Z
            out.append({
                "ticker": qualify(tk),
                "event": str(c.get("event", "")),
                "date": str(c.get("date", "")),
                "value": float(c.get("value")),
            })
    return out


def validate(payload: Dict[str, Any], change_keys: set) -> List[str]:
    """Mirror the receiver schema. Returns a list of offending field labels ([] = ok)."""
    errs: List[str] = []
    rid = payload.get("routine_id")
    if not isinstance(rid, str) or not rid or rid.startswith("PUT_"):
        errs.append("routine_id")
    for i, c in enumerate(payload.get("signal_changes", [])):
        if set(c) != change_keys:
            errs.append("change[%d] keys" % i)
        if c.get("direction") not in ("UP", "DOWN"):
            errs.append("change[%d] direction" % i)
        if not isinstance(c.get("points_delta"), int):
            errs.append("change[%d] points_delta" % i)
        if not (c.get("ticker") and isinstance(c.get("transition"), list) and len(c["transition"]) == 2):
            errs.append("change[%d] ticker/transition" % i)
        if "overlay" in change_keys and c.get("overlay") not in VALID_OVERLAYS:
            errs.append("change[%d] overlay" % i)
    for k, v in payload.get("hard_stops", {}).items():
        if not isinstance(v, float):
            errs.append("hard_stops[%s]" % k)
    for i, c in enumerate(payload.get("catalysts", [])):
        if set(c) != {"ticker", "event", "date", "value"} or not isinstance(c.get("value"), float):
            errs.append("catalyst[%d]" % i)
    for i, t in enumerate(payload.get("portfolio_targets", [])):
        if not isinstance(t, dict) or set(t) != {"symbol", "score"}:
            errs.append("target[%d] keys" % i)
        elif not (isinstance(t.get("symbol"), str) and t["symbol"]):
            errs.append("target[%d] symbol" % i)
        elif isinstance(t.get("score"), bool) or not isinstance(t.get("score"), (int, float)):
            errs.append("target[%d] score" % i)
    return errs


def build_payload(mode: str, run_id: str, raw: Dict[str, Any],
                  timestamp: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], List[str], List[str]]:
    """Build and validate a payload. Returns (payload | None, errs, warnings).

    payload is None iff validation failed (errs non-empty). warnings are non-fatal
    notes (e.g. postures skipped for naming no executable overlay).
    """
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    warnings: List[str] = []
    if mode == "options":
        changes, skipped = build_options_changes(raw.get("postures", []))
        if skipped:
            warnings.append("step-W: %d posture(s) skipped — no executable AutoTrader overlay: %s"
                            % (len(skipped), ", ".join(skipped)))
        payload = {"routine_id": run_id, "timestamp": ts,
                   "signal_changes": changes, "hard_stops": {}, "catalysts": []}
        change_keys = OPTIONS_CHANGE_KEYS
    elif mode == "sweep":
        targets, t_skipped = build_portfolio_targets(raw.get("rows", []))
        if t_skipped:
            warnings.append("step-W: %d target(s) skipped — no usable score: %s"
                            % (len(t_skipped), ", ".join(t_skipped)))
        payload = {"routine_id": run_id, "timestamp": ts,
                   "signal_changes": build_sweep_changes(raw.get("rows", [])),
                   "hard_stops": build_hard_stops(raw.get("stops", [])),
                   "catalysts": build_catalysts(raw.get("catalysts", [])),
                   "portfolio_targets": targets}
        change_keys = SWEEP_CHANGE_KEYS
    else:
        raise ValueError("unknown mode %r (expected 'options' or 'sweep')" % mode)

    errs = validate(payload, change_keys)
    if errs:
        return None, errs, warnings
    return payload, [], warnings


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Build the AutoTrader sweep payload.")
    ap.add_argument("mode", choices=["options", "sweep"])
    ap.add_argument("--run-id", required=True, help="options-YYYYMMDD-HHMM-6hex or routine-...")
    ap.add_argument("--in", dest="infile", help="JSON input file; reads stdin if omitted")
    ap.add_argument("--out", default="/tmp/sweep_payload.json", help="output path (default %(default)s)")
    ap.add_argument("--timestamp", help="override timestamp (mainly for tests)")
    args = ap.parse_args(argv)

    text = open(args.infile).read() if args.infile else sys.stdin.read()
    raw = json.loads(text) if text.strip() else {}

    payload, errs, warnings = build_payload(args.mode, args.run_id, raw, args.timestamp)
    for w in warnings:
        print("[warn] " + w, file=sys.stderr)
    if errs:
        # Mirror the inline builders: write NOTHING so the webhook step skips. Non-fatal.
        print("[warn] step-W validation failed: %s — NOT writing payload, webhook will skip" % errs,
              file=sys.stderr)
        return 0
    with open(args.out, "w") as fh:
        fh.write(json.dumps(payload, separators=(",", ":")))
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
