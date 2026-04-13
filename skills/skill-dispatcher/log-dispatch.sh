#!/bin/bash
# Skill Dispatch Logger Wrapper for Unix/macOS/WSL
# Provides a consistent entry point for logging dispatches

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PYTHON_SCRIPT="$SCRIPT_DIR/scripts/dispatch_logger.py"

if command -v python3 &>/dev/null; then
    python3 "$PYTHON_SCRIPT" "$@"
elif command -v python &>/dev/null; then
    python "$PYTHON_SCRIPT" "$@"
else
    echo "[ERROR] Python 3 could not be found."
    exit 1
fi
