#!/bin/bash
# Skill Dispatcher CLI — unified entry point for routing decisions and execution.
#
# Usage:
#   ./dispatch.sh --query "review my UI" --decide       # routing decision only
#   ./dispatch.sh --query "build a feature" --execute   # decide + execute via orchestrator
#   ./dispatch.sh --query "..." --execute --dry-run     # preview execution plan
#
# For logging a routing event that has already been decided, use log-dispatch.sh instead.

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PYTHON_SCRIPT="$SCRIPT_DIR/scripts/dispatch_cli.py"

if command -v python3 &>/dev/null; then
    python3 "$PYTHON_SCRIPT" "$@"
elif command -v python &>/dev/null; then
    python "$PYTHON_SCRIPT" "$@"
else
    echo "[ERROR] Python 3 could not be found."
    exit 1
fi
