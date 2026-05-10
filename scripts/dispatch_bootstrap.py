#!/usr/bin/env python3
"""Canonical bootstrap entrypoint for policy-aware dispatcher context."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from prepare_dispatch_context import build_payload as build_dispatch_context_payload  # noqa: E402


DEFAULT_TOPIC = "RoutingPolicies"


def resolve_cache_dir(skill_dispatcher_dir: Path, explicit_cache_dir: Optional[str]) -> Path:
    if explicit_cache_dir:
        cache_dir = Path(explicit_cache_dir).expanduser().resolve()
    elif ".agents" in str(skill_dispatcher_dir.resolve()).lower():
        cache_dir = Path.home() / ".agents" / "dispatcher-data" / "registry"
    else:
        cache_dir = skill_dispatcher_dir / "registry"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def build_markdown_note(payload: Dict[str, Any]) -> str:
    policy_lookup = payload["policy_lookup"]
    lines = [
        "# Dispatcher Bootstrap",
        "",
        f"- Topic: `{payload['topic']}`",
        f"- Repo Root: `{payload['repo_root']}`",
        f"- Policy Status: `{policy_lookup['status']}`",
        f"- Policy Source: `{policy_lookup['source']}`",
        f"- Policy Hits: `{policy_lookup['hit_count']}`",
        "- Precedence: `project-memory -> shared-memory`",
        "- Bootstrap Rule: Use this resolved policy context directly instead of separately re-checking project-memory or shared-memory during the same routing step.",
        "",
        "## Resolved Policies",
    ]

    resolved_policies = payload.get("resolved_policies", [])
    if resolved_policies:
        for entry in resolved_policies:
            lines.append(f"- [{entry['policy_source']}] {entry['content']}")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Logger Fields",
            f"- `policy_topic`: `{payload['logger_fields']['policy_topic']}`",
            f"- `policy_status`: `{payload['logger_fields']['policy_status']}`",
            f"- `policy_source`: `{payload['logger_fields']['policy_source']}`",
            f"- `policy_hit_count`: `{payload['logger_fields']['policy_hit_count']}`",
            f"- `policy_applied`: `{str(payload['logger_fields']['policy_applied']).lower()}`",
            f"- `policy_changed_routing`: `{str(payload['logger_fields']['policy_changed_routing']).lower()}`",
        ]
    )

    return "\n".join(lines) + "\n"


def build_bootstrap_payload(
    skill_dispatcher_dir: Path,
    topic: str,
    repo_root: Optional[str],
    project_memory_file: Optional[str],
    shared_min_confidence: float,
    shared_max_age_days: Optional[int],
    shared_include_stale: bool,
    cache_dir: Path,
) -> Dict[str, Any]:
    context_payload = build_dispatch_context_payload(
        skill_dispatcher_dir=skill_dispatcher_dir,
        topic=topic,
        repo_root=repo_root,
        project_memory_file=project_memory_file,
        shared_min_confidence=shared_min_confidence,
        shared_max_age_days=shared_max_age_days,
        shared_include_stale=shared_include_stale,
    )

    markdown_note = build_markdown_note(context_payload)
    return {
        "command": "dispatch-bootstrap",
        "topic": context_payload["topic"],
        "repo_root": context_payload["repo_root"],
        "policy_lookup": context_payload["policy_lookup"],
        "resolved_policies": context_payload["resolved_policies"],
        "precedence": context_payload["precedence"],
        "logger_fields": context_payload["logger_fields"],
        "bootstrap_note": markdown_note,
        "source_payload": context_payload,
        "cache_files": {
            "json": str(cache_dir / "DISPATCH_BOOTSTRAP.json"),
            "markdown": str(cache_dir / "DISPATCH_BOOTSTRAP.md"),
        },
    }


def _log_policy_consult(payload: Dict[str, Any], skill_dispatcher_dir: Path) -> None:
    """Emit a POLICY_CONSULT event to the dispatcher log via dispatch_logger.py.

    Called automatically at the end of main() unless --no-log is passed.
    Failures are silently ignored so bootstrap stays non-blocking.
    """
    logger = skill_dispatcher_dir / "scripts" / "dispatch_logger.py"
    if not logger.exists():
        return

    lf = payload.get("logger_fields", {})
    status = lf.get("policy_status", "miss")
    source = lf.get("policy_source", "none")
    hit_count = str(lf.get("policy_hit_count", 0))
    topic = payload.get("topic", "RoutingPolicies")

    cmd = [
        sys.executable,
        str(logger),
        "--skill", "skill-dispatcher",
        "--intent", "bootstrap_policy_lookup",
        "--decision", "POLICY_CONSULT",
        "--reason", f"bootstrap: {topic} ({status} from {source})",
        "--policy-status", status,
        "--policy-source", source,
        "--policy-hit-count", hit_count,
        "--policy-topic", topic,
    ]
    try:
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            env={**os.environ, "SKILL_DISPATCH_DISABLE_WALLBOARD": "1"},
        )
    except Exception:
        pass


def write_cache(payload: Dict[str, Any]) -> None:
    json_path = Path(payload["cache_files"]["json"])
    markdown_path = Path(payload["cache_files"]["markdown"])
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(payload["bootstrap_note"], encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a single canonical bootstrap note for dispatcher policy context.")
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
        "--cache-dir",
        help="Override the bootstrap cache directory.",
    )
    parser.add_argument(
        "--skip-cache",
        action="store_true",
        help="Do not write DISPATCH_BOOTSTRAP.json / DISPATCH_BOOTSTRAP.md.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
        help="Choose stdout format. JSON is the default.",
    )
    parser.add_argument(
        "--no-log",
        action="store_true",
        help="Skip emitting the automatic POLICY_CONSULT telemetry event.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    skill_dispatcher_dir = Path(__file__).resolve().parent.parent
    cache_dir = resolve_cache_dir(skill_dispatcher_dir, args.cache_dir)
    payload = build_bootstrap_payload(
        skill_dispatcher_dir=skill_dispatcher_dir,
        topic=args.topic,
        repo_root=args.repo_root,
        project_memory_file=args.project_memory_file,
        shared_min_confidence=args.shared_min_confidence,
        shared_max_age_days=args.shared_max_age_days,
        shared_include_stale=args.shared_include_stale,
        cache_dir=cache_dir,
    )

    if not args.skip_cache:
        try:
            write_cache(payload)
        except Exception:
            pass

    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(payload["bootstrap_note"], end="")

    if not args.no_log:
        _log_policy_consult(payload, skill_dispatcher_dir)

    return 0 if payload["policy_lookup"]["status"] != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
