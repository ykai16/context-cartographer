#!/bin/bash

# Get absolute path
INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$INSTALL_DIR/bin"

echo "🦉 Installing Context Cartographer..."

# 1. Make scripts executable
chmod +x "$BIN_DIR/smart_claude.sh"

# 2. Check Python deps
echo "📦 Checking dependencies..."
if ! python3 -c "import openai" &> /dev/null; then
    echo "Installing python 'openai' library..."
    pip install openai
fi

# 3. Setup Alias (ZSH/Bash)
SHELL_RC=""
if [ -n "$ZSH_VERSION" ]; then
    SHELL_RC="$HOME/.zshrc"
elif [ -n "$BASH_VERSION" ]; then
    SHELL_RC="$HOME/.bashrc"
else
    SHELL_RC="$HOME/.profile"
fi

# Add alias if not present
if ! grep -q "alias claude=" "$SHELL_RC"; then
    echo "" >> "$SHELL_RC"
    echo "# Context Cartographer Alias" >> "$SHELL_RC"
    echo "alias claude=\"$BIN_DIR/smart_claude.sh\"" >> "$SHELL_RC"
    echo "✅ Alias 'claude' added to $SHELL_RC"
    echo "👉 Please run: source $SHELL_RC"
else
    echo "ℹ️  Alias 'claude' already exists in $SHELL_RC"
fi

echo "✅ Installation Complete!"
