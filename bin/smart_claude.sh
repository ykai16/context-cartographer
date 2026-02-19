#!/bin/bash

# Configuration
CONTEXT_DIR=".context"
SUMMARY_FILE="$CONTEXT_DIR/session_summary.md"
LOG_FILE="$CONTEXT_DIR/last_session_raw.log"
CARTOGRAPHER_SCRIPT="$(dirname "$0")/cartographer.py"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Ensure context dir exists
mkdir -p "$CONTEXT_DIR"

# --- Phase 1: Pre-flight Check (Resume Context) ---
echo -e "${CYAN}🦉 Context Cartographer active.${NC}"

if [ -f "$SUMMARY_FILE" ]; then
    echo -e "\n${YELLOW}📜 Previously on this project...${NC}"
    echo "---------------------------------------------------"
    # Try to extract the "Context Anchor" section
    if grep -q "# 🧠 Context Anchor" "$SUMMARY_FILE"; then
        grep -A 5 "# 🧠 Context Anchor" "$SUMMARY_FILE" | grep -v "#" | sed '/^\s*$/d'
    else
        head -n 10 "$SUMMARY_FILE"
    fi
    echo -e "---------------------------------------------------\n"
else
    echo -e "✨ Starting a fresh session.\n"
fi

# --- Phase 2: The Session (Recording) ---
# We use 'script' to record everything. 
# Linux uses 'script -c cmd log', MacOS uses 'script -q log cmd'
# Detection logic:
if [[ "$OSTYPE" == "darwin"* ]]; then
    # MacOS
    script -q "$LOG_FILE" /usr/local/bin/claude "$@"
else
    # Linux / Standard
    script -c "/usr/local/bin/claude $*" "$LOG_FILE"
fi

EXIT_CODE=$?

# --- Phase 3: Post-flight Analysis (Generate Map) ---
echo -e "\n\n${GREEN}💾 Session ended. Cartographer is mapping your journey...${NC}"

# Check dependencies
if python3 -c "import openai" &> /dev/null; then
    python3 "$CARTOGRAPHER_SCRIPT" "$LOG_FILE" --out "$SUMMARY_FILE"
    
    if [ -f "$SUMMARY_FILE" ]; then
        echo -e "${CYAN}🗺️  Map Updated! See: $SUMMARY_FILE${NC}"
    fi
else
    echo -e "⚠️  Python dependency 'openai' missing. Run: pip install openai"
    echo -e "   (Raw log saved to $LOG_FILE)"
fi

exit $EXIT_CODE
