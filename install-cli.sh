#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="/usr/local/bin/bb-video-watcher"
FALLBACK="$HOME/bin/bb-video-watcher"

chmod +x "$DIR/cli.py"

if [ -w "/usr/local/bin" ]; then
    ln -sf "$DIR/cli.py" "$TARGET"
    echo "✅ Successfully linked bb-video-watcher to $TARGET"
else
    mkdir -p "$HOME/bin"
    ln -sf "$DIR/cli.py" "$FALLBACK"
    echo "✅ Successfully linked bb-video-watcher to $FALLBACK"
    echo "💡 Ensure $HOME/bin is in your PATH in ~/.zshrc:"
    echo '   export PATH="$HOME/bin:$PATH"'
fi
