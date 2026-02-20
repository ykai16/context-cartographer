#!/bin/bash

# Get directory of this script
BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WRAPPER_SCRIPT="$BIN_DIR/wrapper.py"

# Detect Real Claude path if not set, to pass to python
# This helps the python script avoid aliases
if [ -z "$REAL_CLAUDE_PATH" ]; then
    export REAL_CLAUDE_PATH=$(which -a claude 2>/dev/null | grep -v "smart_claude" | head -n 1)
fi

# Hand over control to the Python PTY wrapper
# It handles everything: recording, interactivity, and analysis
python3 "$WRAPPER_SCRIPT" "$@"