#!/usr/bin/env python3
"""dispatch_cli.py - Unified CLI entry point for skill-dispatcher.

This script does NOT decide routing. The agent does. dispatch_cli prepares
the substrate the agent uses to decide:

  --bootstrap  (default) Run dispatch_bootstrap.py + match_candidates.py and
               return a JSON packet with policy context + scored shortlist.
               The agent reads this packet and picks a skill.

  --execute    Take an already-decided routing JSON and invoke the
               recommended sequence via skill-orchestrator. Requires the
               selected skill to be in the executable allowlist.

Usage:
    python scripts/dispatch_cli.py --query "review my UI code"
    python scripts/dispatch_cli.py --query "build a feature" --intent build_feature
    python scripts/dispatch_cli.py --execute \\
        --routing-decision '{"selected_skill":"angular-developer",...}'

Migration note:
    `--decide` is accepted as a deprecated alias for `--bootstrap`.
    Earlier versions of this script implied `--decide` produced a routing
    decision, which it never did. The fields `decision` and `selected_skill`
    in the old output were misleading stubs and have been removed. Routing
    decisions are made by the agent reading this script's output, not by
    Python.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
CONFIG_DIR = SKILL_ROOT / "config"
ALLOWLIST_PATH = CONFIG_DIR / "executable_skills.json"


def load_allowlist() -> list[str]:
    if not ALLOWLIST_PATH.exists():
        return []
    try:
        data = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
        return [s.strip() for s in data.get("allowed_skills", []) if s.strip()]
    except Exception:
        return []


def run_subscript(name: str, extra_args: list[str]) -> dict:
    """Invoke a sibling script and return its parsed JSON output, or {} on failure."""
    script = SCRIPT_DIR / name
    if not script.exists():
        print(f"[!] {name} not found at {script}", file=sys.stderr)
        return {}
    result = subprocess.run(
        [sys.executable, str(script), *extra_args],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        print(f"[!] {name} exited {result.returncode}: {result.stderr.strip()}", file=sys.stderr)
        return {}
    if not result.stdout.strip():
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        # Fall back: the script printed text, not JSON. Wrap it.
        return {"raw_output": result.stdout.strip()}


def build_bootstrap_packet(query: str, intent: str, topic: str, top_n: int) -> dict:
    """Compose the bootstrap packet: policy context + scored shortlist + agent guidance."""
    bootstrap = run_subscript(
        "dispatch_bootstrap.py",
        ["--topic", topic, "--format", "json"],
    )

    # match_candidates needs an intent. If the caller didn't give us one, we still
    # try to score by treating the query keywords as the intent's hint surface.
    effective_intent = intent or query.replace(" ", "_").lower()[:80]
    candidate_args = [
        "--intent", effective_intent,
        "--keywords", query,
        "--top-n", str(top_n),
        "--format", "json",
    ]
    candidates = run_subscript("match_candidates.py", candidate_args)

    return {
        "command": "dispatch_cli --bootstrap",
        "query": query,
        "intent_used_for_matching": effective_intent,
        "policy": {
            "status": bootstrap.get("policy_lookup", {}).get("status", "skipped"),
            "source": bootstrap.get("policy_lookup", {}).get("source", "none"),
            "hit_count": bootstrap.get("policy_lookup", {}).get("hit_count", 0),
            "resolved": bootstrap.get("resolved_policies", []),
        },
        "shortlist": candidates.get("candidates", []),
        "shortlist_meta": {
            "total_considered": candidates.get("total_considered", 0),
            "after_gates": candidates.get("after_gates", 0),
            "preferred_layer": candidates.get("preferred_layer", ""),
        },
        "agent_guidance": (
            "This packet is substrate, not a decision. Pick a skill from `shortlist` "
            "(or override with a contextual reason worth logging). Then either: "
            "(a) act on it directly, or (b) hand the routing JSON back via "
            "`dispatch_cli.py --execute --routing-decision <json>` to run it through "
            "skill-orchestrator with telemetry."
        ),
    }


def run_orchestrator(routing_decision: dict, dry_run: bool, allowlist: list[str]) -> int:
    """Pass an already-decided routing JSON to skill-orchestrator for execution."""
    selected = routing_decision.get("selected_skill", "none")
    if selected == "none":
        print("[!] --execute requires routing_decision.selected_skill to be set.", file=sys.stderr)
        return 1
    if selected not in allowlist:
        print(
            f"[!] --execute blocked: '{selected}' is not in {ALLOWLIST_PATH}.\n"
            f"    Add it to permit execution.",
            file=sys.stderr,
        )
        return 1

    orchestrate_candidates = [
        SKILL_ROOT.parent / "skill-orchestrator" / "scripts" / "orchestrate.py",
        Path.home() / ".agents" / "skills" / "skill-orchestrator" / "scripts" / "orchestrate.py",
    ]
    orchestrate = next((p for p in orchestrate_candidates if p.exists()), None)
    if orchestrate is None:
        print("[!] --execute: skill-orchestrator not found. Install it alongside skill-dispatcher.", file=sys.stderr)
        return 1

    cmd = [
        sys.executable, str(orchestrate),
        "--routing-decision", json.dumps(routing_decision),
    ]
    if dry_run:
        cmd.append("--dry-run")
        print(f"[dry-run] Would invoke: {' '.join(cmd)}")
        return 0

    return subprocess.run(cmd, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="dispatch_cli: substrate for agent-driven routing. Does not decide.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--bootstrap",
        action="store_true",
        default=True,
        help="(Default) Run dispatch_bootstrap + match_candidates and return the substrate packet for the agent.",
    )
    mode.add_argument(
        "--decide",
        action="store_true",
        help="Deprecated alias for --bootstrap. Earlier versions misleadingly implied this decided routing.",
    )
    mode.add_argument(
        "--execute",
        action="store_true",
        help="Invoke an already-decided routing via skill-orchestrator. Requires --routing-decision.",
    )
    parser.add_argument("--query", default="", help="Natural-language task description (for --bootstrap).")
    parser.add_argument("--intent", default="", help="Normalized routing intent (e.g. 'audit_code'). For --bootstrap.")
    parser.add_argument("--topic", default="RoutingPolicies", help="Policy topic for bootstrap (default: RoutingPolicies).")
    parser.add_argument("--top-n", type=int, default=5, help="How many candidate skills to include in the shortlist.")
    parser.add_argument("--routing-decision", default="", help="Routing JSON for --execute mode.")
    parser.add_argument("--dry-run", action="store_true", help="With --execute: print the orchestrator invocation without running it.")
    args = parser.parse_args()

    # --decide is a deprecated alias; warn but accept
    if args.decide:
        print("[!] --decide is deprecated. Use --bootstrap. See docstring.", file=sys.stderr)

    if args.execute:
        if not args.routing_decision:
            parser.error("--execute requires --routing-decision <json>")
        try:
            decision = json.loads(args.routing_decision)
        except json.JSONDecodeError as exc:
            parser.error(f"--routing-decision is not valid JSON: {exc}")
        return run_orchestrator(decision, args.dry_run, load_allowlist())

    # Default: --bootstrap (or deprecated --decide)
    if not args.query and not args.intent:
        parser.error("--bootstrap requires --query and/or --intent")

    print(f"[*] dispatch_cli --bootstrap: query='{args.query}' intent='{args.intent or '(derived)'}'", file=sys.stderr)
    packet = build_bootstrap_packet(
        query=args.query,
        intent=args.intent,
        topic=args.topic,
        top_n=args.top_n,
    )
    print(json.dumps(packet, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
