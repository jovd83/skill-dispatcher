#!/usr/bin/env python3
"""Suggest shared-memory routing policy promotions from dispatcher telemetry."""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple


def resolve_log_path(skill_dispatcher_dir: Path) -> Path:
    override = os.environ.get("SKILL_DISPATCH_LOG_PATH")
    if override:
        return Path(override).expanduser().resolve()

    persistent_log = Path.home() / ".agents" / "dispatcher-data" / "logs" / "dispatch_events.jsonl"
    local_log = skill_dispatcher_dir / "logs" / "dispatch_events.jsonl"
    if ".agents" in str(skill_dispatcher_dir.resolve()).lower():
        return persistent_log if persistent_log.exists() else local_log
    return local_log if local_log.exists() else persistent_log


def load_events(log_path: Path) -> List[Dict[str, Any]]:
    if not log_path.exists():
        return []
    events: List[Dict[str, Any]] = []
    with log_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip() or line.startswith("#"):
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                continue
    return events


def normalize_skill_chain(event: Dict[str, Any]) -> List[str]:
    skills_used = event.get("skills_used")
    if isinstance(skills_used, list) and skills_used:
        return [str(skill).strip() for skill in skills_used if str(skill).strip()]
    selected_skill = str(event.get("selected_skill", "")).replace("+", ",").replace("&", ",")
    return [part.strip() for part in selected_skill.split(",") if part.strip()]


def build_candidate_statement(intent: str, decision: str, skill_chain: List[str]) -> str:
    if decision == "SEQUENCE" and len(skill_chain) >= 2:
        return (
            f"For intent '{intent}', prefer the sequence "
            f"{' -> '.join(skill_chain)} when repository evidence does not contradict it."
        )
    primary_skill = skill_chain[0] if skill_chain else "the best-fit skill"
    return (
        f"For intent '{intent}', prefer {primary_skill} when repository evidence does not "
        f"suggest a more specific local alternative."
    )


def suggest_promotions(events: List[Dict[str, Any]], threshold: int) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, str, Tuple[str, ...]], List[Dict[str, Any]]] = defaultdict(list)
    for event in events:
        intent = str(event.get("intent", "")).strip()
        decision = str(event.get("decision", "HANDOFF")).strip().upper()
        skill_chain = tuple(normalize_skill_chain(event))
        if not intent or not skill_chain:
            continue
        grouped[(intent, decision, skill_chain)].append(event)

    suggestions: List[Dict[str, Any]] = []
    for (intent, decision, skill_chain), grouped_events in grouped.items():
        if len(grouped_events) < threshold:
            continue
        candidate = build_candidate_statement(intent, decision, list(skill_chain))
        first_seen = grouped_events[0].get("timestamp")
        last_seen = grouped_events[-1].get("timestamp")
        evidence = (
            f"Observed {len(grouped_events)} dispatcher events for intent '{intent}' "
            f"with decision '{decision}'."
        )
        suggestions.append(
            {
                "intent": intent,
                "decision": decision,
                "skills": list(skill_chain),
                "count": len(grouped_events),
                "first_seen": first_seen,
                "last_seen": last_seen,
                "candidate": candidate,
                "evidence": evidence,
                "promote_command": (
                    "py <shared-memory>/scripts/manage_memory.py promote "
                    f"--candidate \"{candidate}\" --topic RoutingPolicies --source SkillDispatcher "
                    "--confidence 0.85 --tags routing,policy --kind policy --review-after-days 365 "
                    "--scope cross-agent --stability stable --sensitivity internal --context-independent yes --format json"
                ),
            }
        )

    suggestions.sort(key=lambda item: (-item["count"], item["intent"], item["decision"]))
    return suggestions


def render_text(suggestions: List[Dict[str, Any]], threshold: int) -> str:
    if not suggestions:
        return f"No routing promotion candidates met the threshold of {threshold} events."
    lines = [f"Routing promotion candidates (threshold: {threshold} events):"]
    for suggestion in suggestions:
        lines.append(
            f"- {suggestion['candidate']} "
            f"[count={suggestion['count']}, skills={' -> '.join(suggestion['skills'])}]"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Suggest shared-memory routing promotions from dispatcher logs.")
    parser.add_argument(
        "--threshold",
        type=int,
        default=3,
        help="Minimum repeated events required before suggesting a promotion candidate.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
        help="Choose stdout format. JSON is the default.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    skill_dispatcher_dir = Path(__file__).resolve().parent.parent
    suggestions = suggest_promotions(load_events(resolve_log_path(skill_dispatcher_dir)), args.threshold)
    payload = {
        "command": "suggest-routing-promotions",
        "threshold": args.threshold,
        "suggestions": suggestions,
    }

    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render_text(suggestions, args.threshold))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
