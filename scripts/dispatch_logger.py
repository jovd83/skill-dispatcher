#!/usr/bin/env python3
"""Skill Dispatch Logger - Records skill invocation events for monitoring."""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def build_auto_policy_lookup(
    skill_dispatcher_dir: Path,
    topic: str,
):
    """Resolve policy lookup metadata automatically for the current routing step."""
    try:
        scripts_dir = Path(__file__).resolve().parent
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        from prepare_dispatch_context import build_payload  # type: ignore

        payload = build_payload(
            skill_dispatcher_dir=skill_dispatcher_dir,
            topic=topic,
            repo_root=os.getcwd(),
            project_memory_file=None,
            shared_min_confidence=0.8,
            shared_max_age_days=365,
            shared_include_stale=False,
        )
        return payload.get("policy_lookup")
    except Exception as exc:
        return {
            "topic": topic,
            "status": "error",
            "source": "none",
            "hit_count": 0,
            "applied": False,
            "changed_routing": False,
            "error": str(exc),
        }

def get_iso_now():
    return datetime.now().isoformat()


def parse_skill_list(raw_value):
    """Normalize a comma/plus/ampersand-delimited skill list."""
    if not raw_value:
        return []

    normalized = raw_value.replace("+", ",").replace("&", ",")
    return [part.strip() for part in normalized.split(",") if part.strip()]


def validate_logging_args(args, parser):
    """Enforce required argument combinations for telemetry integrity."""
    parsed_skills = parse_skill_list(args.skills)
    if args.decision == "SEQUENCE" and not parsed_skills:
        parser.error("--skills is required when --decision SEQUENCE is used.")
    return parsed_skills


def parse_boolish(raw_value):
    if raw_value is None:
        return None
    normalized = str(raw_value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ValueError(f"Unsupported boolean value: {raw_value}")


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
    parser.add_argument(
        "--skills",
        default="",
        help="Comma-separated ordered list of every skill used for this dispatch.",
    )
    parser.add_argument("--intent", required=True, help="The user's original intent.")
    parser.add_argument("--reason", required=True, help="The reason for this selection.")
    parser.add_argument("--decision", default="HANDOFF", choices=["HANDOFF", "SEQUENCE", "NO_MATCH"], help="The type of matching decision made.")
    parser.add_argument(
        "--policy-topic",
        help="Optional policy topic consulted before dispatch, such as RoutingPolicies.",
    )
    parser.add_argument(
        "--policy-status",
        choices=["hit", "miss", "skipped", "error"],
        help="Optional shared/project policy lookup outcome.",
    )
    parser.add_argument(
        "--policy-source",
        choices=["project-memory", "shared-memory", "both", "none"],
        help="Optional source that contributed policy context.",
    )
    parser.add_argument(
        "--policy-hit-count",
        type=int,
        help="Optional number of policy entries returned by the lookup step.",
    )
    parser.add_argument(
        "--policy-applied",
        choices=["true", "false"],
        help="Whether policy context was actually applied to the routing step.",
    )
    parser.add_argument(
        "--policy-changed-routing",
        choices=["true", "false"],
        help="Whether the consulted policy materially changed the routing decision.",
    )
    args = parser.parse_args()
    parsed_skills = validate_logging_args(args, parser)

    # Determine paths
    script_dir = Path(__file__).parent.parent
    config_path = Path(os.environ.get("SKILL_DISPATCH_CONFIG_PATH", script_dir / "config" / "settings.json"))
    
    # SAFE ZONE: Persistent data location outside of the skill installation folder.
    # We use ~/.agents/dispatcher-data/ to survive 'npx skills add' updates.
    persistent_base = Path.home() / ".agents" / "dispatcher-data"
    log_path_override = os.environ.get("SKILL_DISPATCH_LOG_PATH")
    persistent_log_path = Path(log_path_override or (persistent_base / "logs" / "dispatch_events.jsonl"))
    local_log_path = script_dir / "logs" / "dispatch_events.jsonl"
    
    # Smart Discovery & Migration
    if log_path_override:
        log_path = persistent_log_path
    elif ".agents" in str(script_dir.resolve()).lower():
        # Migration: if we have local logs but NO persistent logs yet
        if local_log_path.exists() and not persistent_log_path.exists():
            persistent_log_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                import shutil
                shutil.copy2(local_log_path, persistent_log_path)
                print(f"[*] Migrated logs to Safe Zone: {persistent_log_path}")
            except Exception: pass
        
        log_path = persistent_log_path
    else:
        log_path = local_log_path
        
    if not log_path.parent.exists():
        log_path.parent.mkdir(parents=True, exist_ok=True)

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
    skills_used = parsed_skills or [args.skill]
    if args.skill not in skills_used:
        skills_used.insert(0, args.skill)

    entry = {
        "timestamp": get_iso_now(),
        "selected_skill": args.skill,
        "skills_used": skills_used,
        "intent": args.intent,
        "reason": args.reason,
        "decision": args.decision
    }

    if args.policy_status:
        entry["policy_lookup"] = {
            "topic": args.policy_topic or "RoutingPolicies",
            "status": args.policy_status,
            "source": args.policy_source or "none",
            "hit_count": max(0, args.policy_hit_count or 0),
            "applied": parse_boolish(args.policy_applied) if args.policy_applied is not None else False,
            "changed_routing": (
                parse_boolish(args.policy_changed_routing)
                if args.policy_changed_routing is not None
                else False
            ),
        }
    elif os.environ.get("SKILL_DISPATCH_AUTO_POLICY_LOOKUP", "1") != "0":
        auto_policy_lookup = build_auto_policy_lookup(
            skill_dispatcher_dir=script_dir,
            topic=args.policy_topic or "RoutingPolicies",
        )
        if isinstance(auto_policy_lookup, dict):
            entry["policy_lookup"] = auto_policy_lookup

    # Ensure log directory exists
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Append to log
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    # Auto-Update Wallboard
    generator_path = script_dir / "scripts" / "generate_wallboard.py"
    if generator_path.exists() and os.environ.get("SKILL_DISPATCH_DISABLE_WALLBOARD") != "1":
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
