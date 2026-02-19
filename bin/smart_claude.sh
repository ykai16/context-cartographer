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
    # The command provided to script is executed inside that shell.
    # If it exits immediately, it means the command invocation is wrong or capturing stdin fails.
    
    # CRITICAL FIX for MacOS: 
    # 'script' on MacOS often has issues with interactive curses apps if not handled carefully.
    # The 'command' argument is just a string passed to shell.
    
    # Try interactive mode with /dev/null for input if non-interactive, but here we WANT interactive.
    # We simply execute script with the file. 'script' spawns a shell.
    # To run a SPECIFIC command, we must ensure it's interactive.
    
    # On MacOS, to run an interactive command inside script properly without immediate exit:
    # We just run 'script -q logfile command args...' directly.
    # But arguments handling is tricky.
    
    # Let's try the most robust way: Run 'script' which spawns a shell, and we trap the command execution?
    # No, that's too complex.
    
    # The issue is likely how arguments are passed.
    # Let's quote the command and arguments as a single string for the shell spawned by script.
    
    # Re-assemble command string carefully
    CMD_STRING="$REAL_CLAUDE"
    for arg in "$@"; do
        # Simple quoting for safety
        CMD_STRING="$CMD_STRING \"$arg\""
    done
    
    script -q "$ABS_LOG_FILE" $CMD_STRING
else
    # Linux / Standard (util-linux)
    # Re-assemble command string
    CMD_STRING="$REAL_CLAUDE"
    for arg in "$@"; do
        CMD_STRING="$CMD_STRING \"$arg\""
    done
    
    # The -c flag expects a single string argument for the command
    # And -e returns the exit code of the child
    script -e -c "$CMD_STRING" "$ABS_LOG_FILE"
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
