#!/bin/bash
# Skill Wallboard Generator Wrapper
# Refreshes the visual usage dashboard

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PYTHON_SCRIPT="$SCRIPT_DIR/scripts/generate_wallboard.py"

if command -v python3 &>/dev/null; then
    python3 "$PYTHON_SCRIPT" "$@"
elif command -v python &>/dev/null; then
    python "$PYTHON_SCRIPT" "$@"
else
    echo "[ERROR] Python 3 could not be found."
    exit 1
fi
