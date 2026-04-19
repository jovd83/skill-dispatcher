#!/usr/bin/env python3
"""Prepare routing context from project memory and shared-memory policy."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_TOPIC = "RoutingPolicies"


def normalized_content_key(content: str) -> str:
    return " ".join(content.lower().split())


def resolve_cache_file(skill_dispatcher_dir: Path) -> Path:
    if ".agents" in str(skill_dispatcher_dir.resolve()).lower():
        cache_dir = Path.home() / ".agents" / "dispatcher-data" / "registry"
    else:
        cache_dir = skill_dispatcher_dir / "registry"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "DISPATCH_CONTEXT.json"


def run_json_command(command: List[str], env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or "Unknown command failure."
        raise RuntimeError(stderr)
    return json.loads(result.stdout)


def run_project_memory_lookup(
    skill_dispatcher_dir: Path,
    topic: str,
    repo_root: Optional[str],
    memory_file: Optional[str],
) -> Dict[str, Any]:
    script_path = skill_dispatcher_dir / "scripts" / "project_memory.py"
    if not script_path.exists():
        return {
            "command": "project-memory-read",
            "status": "error",
            "topic": topic,
            "entries": [],
            "error": f"project_memory.py not found at {script_path}",
        }

    command = [sys.executable, str(script_path), "read", "--topic", topic, "--format", "json"]
    if repo_root:
        command.extend(["--repo-root", repo_root])
    if memory_file:
        command.extend(["--memory-file", memory_file])

    try:
        payload = run_json_command(command)
    except Exception as exc:
        return {
            "command": "project-memory-read",
            "status": "error",
            "topic": topic,
            "entries": [],
            "error": str(exc),
        }

    payload["status"] = "hit" if payload.get("entries") else "miss"
    payload["source"] = "project-memory"
    payload["hit_count"] = len(payload.get("entries", []))
    return payload


def run_shared_policy_lookup(
    skill_dispatcher_dir: Path,
    topic: str,
    min_confidence: float,
    max_age_days: Optional[int],
    include_stale: bool,
) -> Dict[str, Any]:
    script_path = skill_dispatcher_dir / "scripts" / "check_shared_policy.py"
    command = [
        sys.executable,
        str(script_path),
        "--topic",
        topic,
        "--min-confidence",
        str(min_confidence),
        "--format",
        "json",
    ]
    if max_age_days is not None:
        command.extend(["--max-age-days", str(max_age_days)])
    if include_stale:
        command.append("--include-stale")

    try:
        payload = run_json_command(command)
    except Exception as exc:
        return {
            "command": "check-shared-policy",
            "status": "error",
            "topic": topic,
            "entries": [],
            "error": str(exc),
            "source": "shared-memory",
        }

    payload["source"] = "shared-memory"
    return payload


def merge_policies(
    project_entries: List[Dict[str, Any]],
    shared_entries: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen = set()

    for source_name, entries in (("project-memory", project_entries), ("shared-memory", shared_entries)):
        for entry in entries:
            key = normalized_content_key(entry.get("content", ""))
            if not key or key in seen:
                continue
            seen.add(key)
            annotated_entry = dict(entry)
            annotated_entry["policy_source"] = source_name
            merged.append(annotated_entry)

    return merged


def compute_policy_source(project_hits: int, shared_hits: int) -> str:
    if project_hits and shared_hits:
        return "both"
    if project_hits:
        return "project-memory"
    if shared_hits:
        return "shared-memory"
    return "none"


def build_payload(
    skill_dispatcher_dir: Path,
    topic: str,
    repo_root: Optional[str],
    project_memory_file: Optional[str],
    shared_min_confidence: float,
    shared_max_age_days: Optional[int],
    shared_include_stale: bool,
) -> Dict[str, Any]:
    project_payload = run_project_memory_lookup(
        skill_dispatcher_dir=skill_dispatcher_dir,
        topic=topic,
        repo_root=repo_root,
        memory_file=project_memory_file,
    )
    shared_payload = run_shared_policy_lookup(
        skill_dispatcher_dir=skill_dispatcher_dir,
        topic=topic,
        min_confidence=shared_min_confidence,
        max_age_days=shared_max_age_days,
        include_stale=shared_include_stale,
    )

    project_entries = project_payload.get("entries", [])
    shared_entries = shared_payload.get("entries", [])
    resolved_policies = merge_policies(project_entries, shared_entries)
    policy_source = compute_policy_source(len(project_entries), len(shared_entries))

    overall_status = "hit" if resolved_policies else "miss"
    if overall_status == "miss" and (
        project_payload.get("status") == "error" or shared_payload.get("status") == "error"
    ):
        overall_status = "error"

    cache_file = resolve_cache_file(skill_dispatcher_dir)
    return {
        "command": "prepare-dispatch-context",
        "topic": topic,
        "repo_root": project_payload.get("repo_root") or repo_root or os.getcwd(),
        "project_memory": project_payload,
        "shared_memory": shared_payload,
        "resolved_policies": resolved_policies,
        "precedence": ["project-memory", "shared-memory"],
        "policy_lookup": {
            "status": overall_status,
            "source": policy_source,
            "hit_count": len(resolved_policies),
            "applied": False,
            "changed_routing": False,
            "topic": topic,
        },
        "logger_fields": {
            "policy_topic": topic,
            "policy_status": overall_status,
            "policy_source": policy_source,
            "policy_hit_count": len(resolved_policies),
            "policy_applied": False,
            "policy_changed_routing": False,
        },
        "cache_file": str(cache_file),
    }


def write_cache(payload: Dict[str, Any]) -> None:
    cache_file = Path(payload["cache_file"])
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render_text(payload: Dict[str, Any]) -> str:
    policy_lookup = payload["policy_lookup"]
    if policy_lookup["status"] == "error":
        return "Dispatcher context preparation encountered an error while gathering policies."
    if policy_lookup["status"] == "miss":
        return f"No dispatcher policies found for topic '{payload['topic']}'."

    lines = [
        f"Prepared dispatcher context for topic '{payload['topic']}' with {policy_lookup['hit_count']} resolved policies.",
        "Precedence: project-memory -> shared-memory",
    ]
    for entry in payload["resolved_policies"]:
        lines.append(f"- [{entry['policy_source']}] {entry['content']}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare policy-aware routing context for the skill dispatcher.")
    parser.add_argument("--topic", default=DEFAULT_TOPIC, help="Policy topic to gather.")
    parser.add_argument("--repo-root", help="Repository root for project-memory lookup.")
    parser.add_argument("--project-memory-file", help="Override the project-memory file path.")
    parser.add_argument(
        "--shared-min-confidence",
        type=float,
        default=0.8,
        help="Shared-memory confidence threshold.",
    )
    parser.add_argument(
        "--shared-max-age-days",
        type=int,
        default=365,
        help="Shared-memory freshness gate in days.",
    )
    parser.add_argument(
        "--shared-include-stale",
        action="store_true",
        help="Include stale shared-memory entries.",
    )
    parser.add_argument(
        "--skip-cache",
        action="store_true",
        help="Do not update the DISPATCH_CONTEXT.json cache file.",
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
    payload = build_payload(
        skill_dispatcher_dir=skill_dispatcher_dir,
        topic=args.topic,
        repo_root=args.repo_root,
        project_memory_file=args.project_memory_file,
        shared_min_confidence=args.shared_min_confidence,
        shared_max_age_days=args.shared_max_age_days,
        shared_include_stale=args.shared_include_stale,
    )

    if not args.skip_cache:
        try:
            write_cache(payload)
        except Exception:
            pass

    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render_text(payload))

    return 0 if payload["policy_lookup"]["status"] != "error" else 1


if __name__ == "__main__":
    sys.exit(main())
