#!/bin/bash

# Configuration
CONTEXT_DIR=".context"
SUMMARY_FILE="$CONTEXT_DIR/session_summary.md"
# Timestamped log file for archiving
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$CONTEXT_DIR/logs/session_$TIMESTAMP.log"
CARTOGRAPHER_SCRIPT="$(dirname "$0")/contextmap.py"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Ensure context and logs dir exists
mkdir -p "$CONTEXT_DIR/logs"

# Resolve ABSOLUTE path for LOG_FILE immediately
# using 'cd' trick to get absolute path of directory, then appending filename
ABS_CONTEXT_DIR=$(cd "$CONTEXT_DIR" && pwd)
ABS_LOG_FILE="$ABS_CONTEXT_DIR/logs/session_$TIMESTAMP.log"
ABS_SUMMARY_FILE="$ABS_CONTEXT_DIR/session_summary.md"

# --- Phase 1: Pre-flight Check (Resume Context) ---
echo -e "${CYAN}🦉 ContextMap active.${NC}"

if [ -f "$ABS_SUMMARY_FILE" ]; then
    echo -e "\n${YELLOW}📜 Previously on this project...${NC}"
    echo "---------------------------------------------------"
    # Try to extract the "Context Anchor" section
    if grep -q "# 🧠 Context Anchor" "$ABS_SUMMARY_FILE"; then
        grep -A 5 "# 🧠 Context Anchor" "$ABS_SUMMARY_FILE" | grep -v "#" | sed '/^\s*$/d'
    else
        head -n 10 "$ABS_SUMMARY_FILE"
    fi
    echo -e "---------------------------------------------------\n"
else
    echo -e "✨ Starting a fresh session.\n"
fi

# ... (omitted) ...

# Detection logic for 'script' command syntax
# NOTE: 'script' behaves differently on BSD/MacOS vs Linux
# MacOS: script -q <file> <command>
# Linux: script -c <command> <file>

if [[ "$OSTYPE" == "darwin"* ]]; then
    # MacOS 'script' creates a sub-shell.
    # We must ensure we're invoking 'script' correctly to keeping the shell interactive.
    # The safest cross-platform way to use 'script' for interactive sessions is actually 
    # NOT to pass the command to it directly (which is flaky), but to start a new shell 
    # inside 'script' and use .bashrc/.zshrc logic to auto-run command? No, too invasive.
    
    # Better approach for MacOS:
    # Use 'SHELL' env var to force script to spawn a shell that executes our command string
    # But script -q log cmd [args] SHOULD work.
    
    # Let's try the simplest approach that works on Mac:
    # script -q logfile /bin/bash -c "cmd args..."
    # This forces a shell context.
    
    # Re-assemble command string
    CMD_STRING="$REAL_CLAUDE"
    for arg in "$@"; do
        CMD_STRING="$CMD_STRING \"$arg\""
    done
    
    # Use 'bash -c' to ensure we have a proper execution context inside script
    # And force pseudo-terminal allocation if needed? No, script does that.
    script -q "$ABS_LOG_FILE" /bin/bash -c "$CMD_STRING"
else
    # Linux / Standard (util-linux)
    # Re-assemble command string
    CMD_STRING="$REAL_CLAUDE"
    for arg in "$@"; do
        CMD_STRING="$CMD_STRING \"$arg\""
    done
    
    # The -c flag expects a single string argument for the command
    # And -e returns the exit code of the child
    # CRITICAL FIX for Linux: 
    # 'script -c cmd' sometimes exits immediately if 'cmd' is not a shell.
    # We force a shell context using 'bash -c' or 'sh -c' to ensure interactive behavior if needed.
    # But usually 'script -c' works. The issue might be finding the binary or TTY allocation.
    # Let's try explicit shell wrapping on Linux too, which is safer.
    
    script -e -q -c "/bin/bash -c '$CMD_STRING'" "$ABS_LOG_FILE"
fi

EXIT_CODE=$?

# --- Phase 3: Post-flight Analysis (Generate Map) ---
echo -e "\n\n${GREEN}💾 Session ended. Cartographer is mapping your journey...${NC}"

# Check dependencies
# We just need Python, no extra libs
# Pass ABSOLUTE PATHs to python script to avoid any ambiguity
CMD_ARGS="'$ABS_LOG_FILE' --out '$ABS_SUMMARY_FILE'"
if [ -n "$MODEL_ARG" ]; then
    echo -e "${CYAN}🧠 Using detected model: $MODEL_ARG${NC}"
    CMD_ARGS="$CMD_ARGS --model $MODEL_ARG"
fi

# Use eval to handle quotes properly in CMD_ARGS
eval python3 \"$CARTOGRAPHER_SCRIPT\" $CMD_ARGS

if [ -f "$ABS_SUMMARY_FILE" ]; then
    echo -e "${CYAN}🗺️  Map Updated! See: $SUMMARY_FILE${NC}"
fi

exit $EXIT_CODE
