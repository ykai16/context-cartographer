#!/bin/bash

# Configuration
CONTEXT_DIR=".context"
SUMMARY_FILE="$CONTEXT_DIR/session_summary.md"
LOG_FILE="$CONTEXT_DIR/last_session_raw.log"
CARTOGRAPHER_SCRIPT="$(dirname "$0")/contextmap.py"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Ensure context dir exists
mkdir -p "$CONTEXT_DIR"

# --- Phase 1: Pre-flight Check (Resume Context) ---
echo -e "${CYAN}🦉 ContextMap active.${NC}"

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

# Find real claude binary (ignoring aliases)
# This is tricky because aliases aren't visible in scripts.
# We assume standard install location or allow override via ENV.
REAL_CLAUDE=${REAL_CLAUDE_PATH:-$(which -a claude 2>/dev/null | grep -v "smart_claude" | head -n 1)}

# Fallback if which fails
if [ -z "$REAL_CLAUDE" ]; then
    # Try common paths
    if [ -x "/usr/local/bin/claude" ]; then
        REAL_CLAUDE="/usr/local/bin/claude"
    elif [ -x "$HOME/.npm-global/bin/claude" ]; then
        REAL_CLAUDE="$HOME/.npm-global/bin/claude"
    else
        echo -e "${YELLOW}⚠️  Could not auto-detect 'claude' binary path.${NC}"
        echo "Please set REAL_CLAUDE_PATH in this script or environment."
        # Fallback to direct call hoping for the best (might loop if alias isn't ignored)
        REAL_CLAUDE="claude"
    fi
fi

# Detect model from arguments
MODEL_ARG=""
for i in "$@"; do
    if [[ "$i" == --model=* ]]; then
        MODEL_ARG="${i#*=}"
    elif [[ "$i" == "-m" ]] && [[ -n "$2" ]]; then
        # This is a simplification; handling next arg properly in bash loop is tricky
        # We rely on simple parsing or assume the user sets it via ENV if complex
        pass 
    fi
done

# If user provided a model flag, capture it
# A robust way to extract the value after -m or --model
while [[ $# -gt 0 ]]; do
  case $1 in
    -m|--model)
      MODEL_ARG="$2"
      shift # past argument
      shift # past value
      ;;
    --model=*)
      MODEL_ARG="${1#*=}"
      shift # past argument
      ;;
    *)
      shift # past argument
      ;;
  esac
done

# Reset positional parameters for the actual command execution
# Note: The loop above consumes args, so we need to run 'script' with the original "$@" 
# But we can't easily restore "$@" after shifting.
# Strategy: Parse FIRST, then run command with original args.

# --- Phase 2: The Session (Recording) ---
# We use 'script' to record everything. 
# Linux uses 'script -c cmd log', MacOS uses 'script -q log cmd'

# Find real claude binary (ignoring aliases)
# ... (existing detection logic) ...

# Detection logic for 'script' command syntax
if [[ "$OSTYPE" == "darwin"* ]]; then
    # MacOS
    script -q "$LOG_FILE" "$REAL_CLAUDE" "$@"
else
    # Linux / Standard
    script -c "$REAL_CLAUDE $*" "$LOG_FILE"
fi

EXIT_CODE=$?

# --- Phase 3: Post-flight Analysis (Generate Map) ---
echo -e "\n\n${GREEN}💾 Session ended. Cartographer is mapping your journey...${NC}"

# Check dependencies
if python3 -c "import openai" &> /dev/null || python3 -c "import boto3" &> /dev/null; then
    # Pass the detected model to the analyzer
    CMD_ARGS="$LOG_FILE --out $SUMMARY_FILE"
    if [ -n "$MODEL_ARG" ]; then
        echo -e "${CYAN}🧠 Using detected model: $MODEL_ARG${NC}"
        CMD_ARGS="$CMD_ARGS --model $MODEL_ARG"
    fi
    
    python3 "$CARTOGRAPHER_SCRIPT" $CMD_ARGS
    
    if [ -f "$SUMMARY_FILE" ]; then
        echo -e "${CYAN}🗺️  Map Updated! See: $SUMMARY_FILE${NC}"
    fi
else
    echo -e "⚠️  Python dependency 'openai' or 'boto3' missing."
    echo -e "   (Raw log saved to $LOG_FILE)"
fi

exit $EXIT_CODE
