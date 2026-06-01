#!/usr/bin/env bash
# Sync scripts/trade_schemas.py → proxy/_lib/trade_schemas.py
#
# The proxy vendors a bit-identical copy of the schema module so the
# Vercel deploy is self-contained (no `vercel.json includeFiles` that
# reach outside the project root). Run this every time you edit
# scripts/trade_schemas.py; the D.17 gate (see CLAUDE.md cross-file
# contracts) will reject commits where the two files diverge.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SRC="$ROOT/scripts/trade_schemas.py"
DST="$ROOT/proxy/_lib/trade_schemas.py"

if [ ! -f "$SRC" ]; then
    echo "[fatal] canonical $SRC not found" >&2
    exit 1
fi

cp "$SRC" "$DST"

if diff -q "$SRC" "$DST" > /dev/null; then
    echo "  ✓ synced scripts/trade_schemas.py → proxy/_lib/trade_schemas.py (bit-identical)"
else
    echo "  ✗ post-copy diff is non-empty — filesystem race?" >&2
    diff "$SRC" "$DST" >&2 || true
    exit 1
fi
