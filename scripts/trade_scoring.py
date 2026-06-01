#!/usr/bin/env python3
"""
Shared scoring helpers for the AI Trading Analyst plugin.

Single source of truth for the 6-band score → grade → signal table used by:
- `scripts/generate_trade_pdf.py` (PDF report rendering)
- `scripts/trade_memory.py` (Pinecone metadata write path — slice 3a)
- Any future consumer of the canonical grade/signal mapping

The canonical 6-band table (mirrored in `trade/SKILL.md:57-64`,
`skills/trade-analyze/SKILL.md` interpretation table, `README.md` grade-signal
table, and `plan/portfolio-routine-and-vector-memory.md` §7):

    Score    Grade   Signal (UPPERCASE form used in metadata storage)
    -------  ------  --------------------------------------------------
    85-100   A+      STRONG BUY
    70-84    A       BUY
    55-69    B       HOLD
    40-54    C       NEUTRAL
    25-39    D       CAUTION
    0-24     F       AVOID

UPPERCASE labels are the canonical in-Python form. Prose documents may render
in mixed case ("Strong Buy", "Hold/Accumulate") for human readability, but the
metadata storage path (Pinecone records, frontmatter parsing) uses UPPERCASE
exactly — see `plan/portfolio-routine-and-vector-memory.md` §1 Consumer Integration
contract for the rule.

Grades are single-letter only — no `B+`, `C+`, `C-`, `D+`. See M4 cleanup in
`plan/portfolio-routine-and-vector-memory.md` §7 and the Consumer Integration
field-contract table.
"""


def score_grade(score):
    """Return single-letter trade grade from a composite score (0-100).

    Returns one of exactly 6 values: "A+", "A", "B", "C", "D", "F".
    """
    if score >= 85:
        return "A+"
    elif score >= 70:
        return "A"
    elif score >= 55:
        return "B"
    elif score >= 40:
        return "C"
    elif score >= 25:
        return "D"
    else:
        return "F"


def trade_signal(score):
    """Return UPPERCASE trade signal from a composite score (0-100).

    Returns one of exactly 6 values:
        "STRONG BUY", "BUY", "HOLD", "NEUTRAL", "CAUTION", "AVOID".

    The 40-54 band is "NEUTRAL" (not "CAUTION" — that was the pre-slice-1
    5-band bug); 25-39 is "CAUTION".
    """
    if score >= 85:
        return "STRONG BUY"
    elif score >= 70:
        return "BUY"
    elif score >= 55:
        return "HOLD"
    elif score >= 40:
        return "NEUTRAL"
    elif score >= 25:
        return "CAUTION"
    else:
        return "AVOID"


if __name__ == "__main__":
    # Self-test: routing the 6 boundary scores produces the canonical labels.
    # This is the slice-1 gate verification (plan §7 gate item 3).
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
        if not ok_g:
            failures.append(f"score={score}: grade got {got_grade!r}, want {want_grade!r}")
        if not ok_s:
            failures.append(f"score={score}: signal got {got_signal!r}, want {want_signal!r}")
    if failures:
        print("\nFAILED:")
        for f in failures:
            print(f"  - {f}")
        raise SystemExit(1)
    print("\nAll 6 boundary cases pass.")
