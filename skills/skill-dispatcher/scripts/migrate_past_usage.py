#!/usr/bin/env python3
"""Skill Dispatch Migrator - Bootstraps usage logs from past session history."""

import json
import os
import re
from pathlib import Path
from datetime import datetime

# Path to session logs
SESSIONS_ROOT = Path(r"C:\Users\jochi\.codex\sessions")
# Regex to match dispatcher outputs - more robust for legacy logs
DECISION_REGEX = re.compile(r"(?:\*\*|__)?Decision(?:\*\*|__)?:\s*(HANDOFF|SEQUENCE|NO_MATCH)", re.IGNORECASE)
SKILL_REGEX = re.compile(r"(?:\*\*|__)?Selected skill(?:\*\*|__)?:\s*(.+)", re.IGNORECASE)
INTENT_REGEX = re.compile(r"(?:\[Intent\]|Intent:)\s*(.+)", re.IGNORECASE)
REASON_REGEX = re.compile(r"(?:\[Mapping\]|Reason:)\s*(.+)", re.IGNORECASE)

def get_iso_now():
    return datetime.now().isoformat()

def parse_jsonl_session(file_path):
    events = []
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            try:
                data = json.loads(line)
                # We look for assistant messages containing "Decision:"
                if data.get("type") == "response_item":
                    payload = data.get("payload", {})
                    if payload.get("type") == "message" and payload.get("role") == "assistant":
                        for content_item in payload.get("content", []):
                            text = content_item.get("text", "")
                            # Check for Decision in any casing
                            if "decision" in text.lower():
                                decision_match = DECISION_REGEX.search(text)
                                skill_match = SKILL_REGEX.search(text)
                                intent_match = INTENT_REGEX.search(text)
                                reason_match = REASON_REGEX.search(text)

                                if decision_match and skill_match:
                                    events.append({
                                        "timestamp": data.get("timestamp"),
                                        "selected_skill": skill_match.group(1).strip().replace("**", "").replace("__", ""),
                                        "intent": intent_match.group(1).strip() if intent_match else "Recovered from history",
                                        "reason": reason_match.group(1).strip() if reason_match else "Recovered from history",
                                        "decision": decision_match.group(1).strip().upper()
                                    })
            except Exception:
                continue
    return events

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Skill Dispatch Migrator")
    parser.add_argument("--sample", action="store_true", help="Generate sample data if none found")
    args = parser.parse_args()

    print("=== Skill Dispatch Migrator ===")
    print(f"[*] Scanning sessions at: {SESSIONS_ROOT}")
    
    all_events = []
    if SESSIONS_ROOT.exists():
        # Walk through year/month/day folders
        for root, dirs, files in os.walk(SESSIONS_ROOT):
            for file in files:
                if file.endswith(".jsonl"):
                    full_path = Path(root) / file
                    events = parse_jsonl_session(full_path)
                    if events:
                        print(f"[*] Found {len(events)} events in {file}")
                        all_events.extend(events)

    if not all_events:
        print("[!] No past events found in session history.")
        if args.sample:
            print("[*] Generating sample data as requested...")
            all_events = [
                {"timestamp": get_iso_now(), "selected_skill": "skill-creator", "intent": "How do I make a skill?", "reason": "System bootstrap", "decision": "HANDOFF"},
                {"timestamp": get_iso_now(), "selected_skill": "playwright-skill", "intent": "Run E2E tests", "reason": "Testing request", "decision": "HANDOFF"},
                {"timestamp": get_iso_now(), "selected_skill": "shadcn-ui", "intent": "Add a button component", "reason": "UI request", "decision": "HANDOFF"},
                {"timestamp": get_iso_now(), "selected_skill": "frontend-design", "intent": "Make the dashboard look premium", "reason": "Aesthetics request", "decision": "HANDOFF"}
            ]
        else:
            print("[Tip] Run with --sample to generate demonstration data.")
            return

    # Sort by timestamp
    all_events.sort(key=lambda x: x["timestamp"])

    # Output path
    script_dir = Path(__file__).parent.parent
    log_path = script_dir / "logs" / "dispatch_events.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Deduced counts
    print(f"[*] Total events for migration: {len(all_events)}")
    
    with open(log_path, "a", encoding="utf-8") as f:
        for ev in all_events:
            f.write(json.dumps(ev) + "\n")
            
    print(f"[*] Successfully populated usage log at: {log_path}")

if __name__ == "__main__":
    main()
