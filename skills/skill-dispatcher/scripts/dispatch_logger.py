#!/usr/bin/env python3
"""Skill Dispatch Logger - Records skill invocation events for monitoring."""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

def get_iso_now():
    return datetime.now().isoformat()

def check_environment():
    """Check if we are running in a potentially problematic environment (like MS Store stub)."""
    exe = sys.executable.lower()
    if "windowsapps" in exe and "python" in exe:
        print("[WARNING] Running via Microsoft Store Python stub. This may cause execution issues.")
        print("Tip: Disable 'App execution aliases' for Python in Windows Settings or install Python from python.org.")

def main():
    check_environment()
    parser = argparse.ArgumentParser(description="Log a skill dispatch event.")
    parser.add_argument("--skill", required=True, help="The name of the selected skill.")
    parser.add_argument("--intent", required=True, help="The user's original intent.")
    parser.add_argument("--reason", required=True, help="The reason for this selection.")
    args = parser.parse_args()

    # Determine paths relative to this script
    script_dir = Path(__file__).parent.parent
    config_path = script_dir / "config" / "settings.json"
    log_path = script_dir / "logs" / "dispatch_events.jsonl"

    # Check feature flag
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
                if not settings.get("logging_enabled", True):
                    return # Logging is disabled
        except Exception:
            pass # Default to enabled if error reading config

    # Prepare log entry
    entry = {
        "timestamp": get_iso_now(),
        "selected_skill": args.skill,
        "intent": args.intent,
        "reason": args.reason
    }

    # Ensure log directory exists
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Append to log
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    # Auto-Update Wallboard
    generator_path = script_dir / "scripts" / "generate_wallboard.py"
    if generator_path.exists():
        try:
            # Run generator as a background task
            # Use sys.executable to ensure we use the same python interpreter
            subprocess.Popen([sys.executable, str(generator_path)], 
                             stdout=subprocess.DEVNULL, 
                             stderr=subprocess.DEVNULL)
        except Exception:
            pass # Non-blocking failure

if __name__ == "__main__":
    main()
