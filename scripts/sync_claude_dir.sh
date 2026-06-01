#!/usr/bin/env bash
# Mirror skills/ + trade/ → .claude/skills/ (authoritative; uses --delete so the
# mirror is byte-for-byte the source). Additively sync agents/ → .claude/agents/
# (non-trade agents preserved; NO --delete to avoid wiping non-trade agents that
# legitimately live only under .claude/agents/, per producer plan §3).
#
# Idempotent: re-running produces no changes when sources are unchanged.
#
# See `plan/portfolio-routine-and-vector-memory.md` §3 for design rationale and
# §8 slice 2 for the rollout context. `install.sh` calls this script as its
# first step (slice 9 polish); contributors should also re-run it after editing
# any skill or agent (per `CLAUDE.md`).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$ROOT/.claude/skills" "$ROOT/.claude/agents"
rsync -a --delete "$ROOT/skills/" "$ROOT/.claude/skills/"
rsync -a          "$ROOT/agents/" "$ROOT/.claude/agents/"
rsync -a --delete "$ROOT/trade/"  "$ROOT/.claude/skills/trade/"
echo "synced .claude/ from skills/, agents/ (additive), trade/"
