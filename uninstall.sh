#!/bin/bash
# ============================================================================
# AI Trading Analyst — Uninstaller
# ============================================================================
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SKILLS_DIR="$HOME/.claude/skills"
AGENTS_DIR="$HOME/.claude/agents"

echo ""
echo -e "${BLUE}Uninstalling AI Trading Analyst...${NC}"
echo ""

# Remove skills (must stay in sync with install.sh SKILLS array — 19 total)
SKILLS=(
    trade
    trade-analyze
    trade-technical
    trade-fundamental
    trade-sentiment
    trade-sector
    trade-compare
    trade-thesis
    trade-options
    trade-portfolio
    trade-holdings
    trade-routine
    trade-recall
    trade-risk
    trade-screen
    trade-earnings
    trade-watchlist
    trade-report-pdf
    trade-quick
)

for skill in "${SKILLS[@]}"; do
    if [ -d "$SKILLS_DIR/$skill" ]; then
        rm -rf "$SKILLS_DIR/$skill"
        echo -e "  ${GREEN}✓${NC} Removed $skill"
    fi
done

# Remove agents
AGENTS=(
    trade-technical
    trade-fundamental
    trade-sentiment
    trade-risk
    trade-thesis
)

for agent in "${AGENTS[@]}"; do
    if [ -f "$AGENTS_DIR/$agent.md" ]; then
        rm "$AGENTS_DIR/$agent.md"
        echo -e "  ${GREEN}✓${NC} Removed agent: $agent"
    fi
done

# Note: $SKILLS_DIR/trade/ may still contain the scripts/ subdirectory
# (trade_memory.py, trade_scoring.py, trade_schemas.py, sync_*.sh) installed
# by install.sh into $SKILLS_DIR/trade/scripts/. The rm -rf above on
# $SKILLS_DIR/trade removes everything under it, scripts included.
# No separate cleanup needed.

# Note: the user's ~/.claude/trade/ cache directory (TRADE-HOLDINGS.md fallback
# cache, written by the trade-holdings skill at runtime) is NOT removed here —
# it lives outside SKILLS_DIR and may contain user data. Delete manually if you
# also want to wipe the holdings cache:
#     rm -rf ~/.claude/trade/

echo ""
echo -e "${GREEN}Uninstall complete.${NC} All AI Trading Analyst skills and agents have been removed."
echo -e "Your Claude Code installation is otherwise unchanged."
echo ""
echo -e "${YELLOW}Note:${NC} the holdings cache at ${BLUE}~/.claude/trade/${NC} (if present) was kept."
echo -e "Remove manually with: ${BLUE}rm -rf ~/.claude/trade/${NC}"
echo ""
