#!/bin/bash
# Skill Dispatcher Diagnostics for Unix/macOS
echo "Skill Dispatcher Diagnostics"
echo "============================"
echo ""

echo "[1] Checking Python environment..."
if command -v python3 &>/dev/null; then
    echo "[OK] python3 found."
    python3 --version
elif command -v python &>/dev/null; then
    echo "[OK] python found."
    python --version
else
    echo "[FAIL] Python NOT found."
fi

echo ""
echo "[2] Checking Project Structure..."
if [ -f "scripts/dispatch_logger.py" ]; then
    echo "[OK] dispatch_logger.py found."
else
    echo "[FAIL] dispatch_logger.py NOT found. Are you in the skill-dispatcher directory?"
fi

echo ""
echo "[3] Checking Config..."
if [ -f "config/settings.json" ]; then
    echo "[OK] settings.json found."
else
    echo "[WARN] settings.json NOT found."
fi

echo ""
echo "Done."
