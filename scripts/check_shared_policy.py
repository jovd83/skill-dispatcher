#!/usr/bin/env python3
"""Query shared-memory for cross-project routing policies."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_TOPIC = "RoutingPolicies"


def candidate_registry_paths(skill_dispatcher_dir: Path) -> List[Path]:
    persistent_registry = Path.home() / ".agents" / "dispatcher-data" / "registry" / "SKILL_REGISTRY.json"
    local_registry = skill_dispatcher_dir / "registry" / "SKILL_REGISTRY.json"
    paths = [persistent_registry, local_registry]
    return [path for path in paths if path.exists()]


def load_registry(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_shared_memory_path(skill_dispatcher_dir: Path) -> Optional[Path]:
    env_override = os.environ.get("SKILL_DISPATCH_SHARED_MEMORY_DIR")
    if env_override:
        candidate = Path(env_override).expanduser().resolve()
        if candidate.exists():
            return candidate

    for registry_path in candidate_registry_paths(skill_dispatcher_dir):
        registry = load_registry(registry_path)
        for skill in registry.get("skills", []):
            if skill.get("name") == "shared-memory":
                location = skill.get("location")
                if location:
                    candidate = Path(location).expanduser().resolve()
                    if candidate.exists():
                        return candidate

    sibling = skill_dispatcher_dir.parent / "shared-memory"
    if sibling.exists():
        return sibling.resolve()

    return None


def resolve_cache_file(skill_dispatcher_dir: Path) -> Path:
    if ".agents" in str(skill_dispatcher_dir.resolve()).lower():
        cache_dir = Path.home() / ".agents" / "dispatcher-data" / "registry"
    else:
        cache_dir = skill_dispatcher_dir / "registry"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "SHARED_ADVICE.json"


def run_manage_memory(shared_memory_dir: Path, command_args: List[str]) -> Dict[str, Any]:
    manage_script = shared_memory_dir / "scripts" / "manage_memory.py"
    if not manage_script.exists():
        raise FileNotFoundError(f"manage_memory.py not found at {manage_script}")

    result = subprocess.run(
        [sys.executable, str(manage_script), *command_args, "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or "Unknown shared-memory CLI failure."
        raise RuntimeError(stderr)
    return json.loads(result.stdout)


def build_payload(
    skill_dispatcher_dir: Path,
    topic: str,
    min_confidence: float,
    max_age_days: Optional[int],
    include_deprecated: bool,
    include_stale: bool,
) -> Dict[str, Any]:
    shared_memory_dir = get_shared_memory_path(skill_dispatcher_dir)
    cache_file = resolve_cache_file(skill_dispatcher_dir)
    payload: Dict[str, Any] = {
        "command": "check-shared-policy",
        "topic": topic,
        "status": "miss",
        "source": "shared-memory",
        "filters": {
            "min_confidence": min_confidence,
            "max_age_days": max_age_days,
            "include_deprecated": include_deprecated,
            "include_stale": include_stale,
        },
        "entries": [],
        "cache_file": str(cache_file),
    }

    if not shared_memory_dir:
        payload["status"] = "error"
        payload["error"] = "shared-memory skill not found in the registry or sibling directories."
        return payload

    payload["shared_memory_dir"] = str(shared_memory_dir)

    command_args = ["read", "--topic", topic, "--min-confidence", str(min_confidence)]
    if max_age_days is not None:
        command_args.extend(["--max-age-days", str(max_age_days)])
    if include_deprecated:
        command_args.append("--include-deprecated")
    if include_stale:
        command_args.append("--include-stale")

    try:
        result = run_manage_memory(shared_memory_dir, command_args)
    except Exception as exc:
        payload["status"] = "error"
        payload["error"] = str(exc)
        return payload

    payload["memory_file"] = result.get("memory_file")
    payload["entries"] = result.get("entries", [])
    payload["filters"] = result.get("filters", payload["filters"])
    payload["skipped"] = result.get("skipped", {})
    payload["status"] = "hit" if payload["entries"] else "miss"
    payload["hit_count"] = len(payload["entries"])
    return payload


def write_cache(payload: Dict[str, Any]) -> None:
    cache_file = Path(payload["cache_file"])
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render_text(payload: Dict[str, Any]) -> str:
    status = payload["status"]
    if status == "error":
        return f"Shared policy lookup failed: {payload.get('error', 'unknown error')}"
    if status == "miss":
        return f"No shared routing policies matched topic '{payload['topic']}'."

    lines = [
        f"Shared policy lookup hit for topic '{payload['topic']}' ({payload['hit_count']} entries).",
    ]
    for entry in payload.get("entries", []):
        lines.append(
            f"- #{entry['id']} {entry['content']} "
            f"(confidence: {entry['confidence']}, age_days: {entry.get('age_days', 'n/a')})"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read shared-memory routing policies with freshness and confidence gates.")
    parser.add_argument("--topic", default=DEFAULT_TOPIC, help="Shared-memory topic to read.")
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.8,
        help="Filter out entries below this confidence threshold.",
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=365,
        help="Filter out entries older than this many days unless --include-stale is set.",
    )
    parser.add_argument(
        "--include-deprecated",
        action="store_true",
        help="Include deprecated entries in the lookup result.",
    )
    parser.add_argument(
        "--include-stale",
        action="store_true",
        help="Include stale entries that would normally be filtered out.",
    )
    parser.add_argument(
        "--skip-cache",
        action="store_true",
        help="Do not update the SHARED_ADVICE.json cache file.",
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
        min_confidence=args.min_confidence,
        max_age_days=args.max_age_days,
        include_deprecated=args.include_deprecated,
        include_stale=args.include_stale,
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

    return 0 if payload["status"] != "error" else 1


if __name__ == "__main__":
    sys.exit(main())
