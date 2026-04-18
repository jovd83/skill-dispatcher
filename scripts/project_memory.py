#!/usr/bin/env python3
"""Project-local routing memory for the skill dispatcher."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA_VERSION = "1.0"
ACTIVE_STATUS = "active"
DEPRECATED_STATUS = "deprecated"
VALID_STATUSES = {ACTIVE_STATUS, DEPRECATED_STATUS}


class ProjectMemoryError(Exception):
    exit_code = 1


class InputValidationError(ProjectMemoryError):
    exit_code = 2


class MissingEntryError(ProjectMemoryError):
    exit_code = 3


class StoreFormatError(ProjectMemoryError):
    exit_code = 4


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def find_repo_root(start_path: Optional[str]) -> Path:
    current = Path(start_path or os.getcwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    return current


def resolve_repo_root(explicit_repo_root: Optional[str]) -> Path:
    if explicit_repo_root:
        return Path(explicit_repo_root).expanduser().resolve()
    env_root = os.environ.get("AGENT_PROJECT_MEMORY_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return find_repo_root(None)


def resolve_memory_file(explicit_path: Optional[str], repo_root: Path) -> Path:
    if explicit_path:
        return Path(explicit_path).expanduser().resolve()
    env_path = os.environ.get("AGENT_PROJECT_MEMORY_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return repo_root / ".agents" / "project_memory.json"


def ensure_topic_name(topic: str) -> str:
    cleaned = topic.strip()
    if not cleaned:
        raise InputValidationError("Topic must not be empty.")
    if len(cleaned) > 80:
        raise InputValidationError("Topic must be 80 characters or fewer.")
    return cleaned


def ensure_source(source: str) -> str:
    cleaned = source.strip()
    if not cleaned:
        raise InputValidationError("Source must not be empty.")
    return cleaned


def ensure_content(content: str) -> str:
    cleaned = " ".join(content.split())
    if not cleaned:
        raise InputValidationError("Content must not be empty.")
    return cleaned


def ensure_confidence(confidence: float) -> float:
    value = float(confidence)
    if not 0.0 <= value <= 1.0:
        raise InputValidationError("Confidence must be between 0.0 and 1.0.")
    return round(value, 4)


def normalize_tags(raw_tags: Optional[Any]) -> List[str]:
    if raw_tags is None:
        return []
    if isinstance(raw_tags, str):
        items = raw_tags.split(",")
    elif isinstance(raw_tags, list):
        items = raw_tags
    else:
        raise InputValidationError("Tags must be a comma-separated string or list of strings.")

    normalized: List[str] = []
    seen = set()
    for item in items:
        tag = str(item).strip()
        if not tag:
            continue
        lowered = tag.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(tag)
    return normalized


def normalize_kind(kind: Optional[str]) -> Optional[str]:
    if kind is None:
        return None
    cleaned = kind.strip().lower().replace(" ", "-")
    if not cleaned:
        return None
    if len(cleaned) > 40:
        raise InputValidationError("Kind must be 40 characters or fewer.")
    return cleaned


def normalized_content_key(content: str) -> str:
    return " ".join(content.lower().split())


def default_store(repo_root: Path) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "repo_root": str(repo_root),
        "topics": {},
    }


def normalize_entry(topic: str, raw_entry: Dict[str, Any], fallback_id: int) -> Dict[str, Any]:
    if not isinstance(raw_entry, dict):
        raise StoreFormatError(f"Entry in topic '{topic}' must be a JSON object.")

    try:
        entry_id = int(raw_entry.get("id", fallback_id))
    except (TypeError, ValueError) as exc:
        raise StoreFormatError(f"Entry id in topic '{topic}' must be an integer.") from exc

    status = raw_entry.get("status", ACTIVE_STATUS)
    if raw_entry.get("deprecated") is True:
        status = DEPRECATED_STATUS
    if status not in VALID_STATUSES:
        raise StoreFormatError(f"Entry id {entry_id} in topic '{topic}' has invalid status '{status}'.")

    created_at = raw_entry.get("created_at") or raw_entry.get("timestamp")
    if not created_at:
        raise StoreFormatError(f"Entry id {entry_id} in topic '{topic}' is missing a timestamp.")

    normalized = {
        "id": entry_id,
        "status": status,
        "created_at": str(created_at),
        "source": ensure_source(str(raw_entry.get("source", ""))),
        "confidence": ensure_confidence(float(raw_entry.get("confidence", 1.0))),
        "content": ensure_content(str(raw_entry.get("content", ""))),
        "tags": normalize_tags(raw_entry.get("tags")),
    }

    kind = normalize_kind(raw_entry.get("kind"))
    if kind:
        normalized["kind"] = kind

    evidence = raw_entry.get("evidence")
    if evidence:
        normalized["evidence"] = str(evidence).strip()

    deprecated_at = raw_entry.get("deprecated_at")
    if deprecated_at:
        normalized["deprecated_at"] = str(deprecated_at)

    deprecation_reason = raw_entry.get("deprecation_reason")
    if deprecation_reason:
        normalized["deprecation_reason"] = str(deprecation_reason).strip()

    return normalized


def normalize_store(raw_data: Dict[str, Any], repo_root: Path) -> Dict[str, Any]:
    if not isinstance(raw_data, dict):
        raise StoreFormatError("Project memory file must contain a JSON object.")

    topics_raw = raw_data.get("topics", {})
    if not isinstance(topics_raw, dict):
        raise StoreFormatError("'topics' must be a JSON object.")

    normalized_topics: Dict[str, List[Dict[str, Any]]] = {}
    for raw_topic, raw_entries in topics_raw.items():
        topic = ensure_topic_name(str(raw_topic))
        if not isinstance(raw_entries, list):
            raise StoreFormatError(f"Topic '{topic}' must map to a list of entries.")
        entries = [normalize_entry(topic, entry, index) for index, entry in enumerate(raw_entries, start=1)]
        entries.sort(key=lambda item: item["id"])
        normalized_topics[topic] = entries

    return {
        "schema_version": SCHEMA_VERSION,
        "repo_root": str(repo_root),
        "topics": normalized_topics,
    }


def load_store(memory_file: Path, repo_root: Path) -> Dict[str, Any]:
    if not memory_file.exists():
        return default_store(repo_root)
    try:
        raw_text = memory_file.read_text(encoding="utf-8")
        raw_data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise StoreFormatError(f"Project memory file '{memory_file}' is not valid JSON: {exc}") from exc
    except OSError as exc:
        raise StoreFormatError(f"Unable to read project memory file: {exc}") from exc
    return normalize_store(raw_data, repo_root)


def save_store(memory_file: Path, store: Dict[str, Any]) -> None:
    memory_file.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(store, indent=2, ensure_ascii=False) + "\n"
    temp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            delete=False,
            dir=str(memory_file.parent),
            encoding="utf-8",
            prefix=".project-memory-",
            suffix=".json",
        ) as handle:
            handle.write(payload)
            temp_path = handle.name
        os.replace(temp_path, memory_file)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def count_entries(entries: List[Dict[str, Any]]) -> Dict[str, int]:
    active_entries = [entry for entry in entries if entry["status"] == ACTIVE_STATUS]
    deprecated_entries = [entry for entry in entries if entry["status"] == DEPRECATED_STATUS]
    return {
        "active_entries": len(active_entries),
        "deprecated_entries": len(deprecated_entries),
        "total_entries": len(entries),
    }


def list_topics(store: Dict[str, Any], memory_file: Path, repo_root: Path) -> Dict[str, Any]:
    topics = []
    for topic in sorted(store["topics"]):
        topics.append({"topic": topic, **count_entries(store["topics"][topic])})
    return {
        "command": "list-topics",
        "schema_version": SCHEMA_VERSION,
        "memory_file": str(memory_file),
        "repo_root": str(repo_root),
        "topics": topics,
    }


def read_topic(
    store: Dict[str, Any],
    memory_file: Path,
    repo_root: Path,
    topic: str,
    include_deprecated: bool,
) -> Dict[str, Any]:
    topic_name = ensure_topic_name(topic)
    entries = store["topics"].get(topic_name, [])
    filtered = [entry for entry in entries if include_deprecated or entry["status"] != DEPRECATED_STATUS]
    return {
        "command": "read",
        "schema_version": SCHEMA_VERSION,
        "memory_file": str(memory_file),
        "repo_root": str(repo_root),
        "topic": topic_name,
        "entries": filtered,
    }


def search_entries(
    store: Dict[str, Any],
    memory_file: Path,
    repo_root: Path,
    query: str,
    include_deprecated: bool,
    limit: int,
) -> Dict[str, Any]:
    query_text = query.strip().lower()
    if not query_text:
        raise InputValidationError("Search query must not be empty.")

    matches = []
    for topic in sorted(store["topics"]):
        for entry in store["topics"][topic]:
            if not include_deprecated and entry["status"] == DEPRECATED_STATUS:
                continue
            haystack = " ".join(
                [topic, entry["content"], entry["source"], " ".join(entry.get("tags", []))]
            ).lower()
            if query_text not in haystack:
                continue
            matches.append({"topic": topic, "entry": entry})
            if len(matches) >= limit:
                break
        if len(matches) >= limit:
            break

    return {
        "command": "search",
        "schema_version": SCHEMA_VERSION,
        "memory_file": str(memory_file),
        "repo_root": str(repo_root),
        "query": query,
        "matches": matches,
    }


def write_entry(
    store: Dict[str, Any],
    memory_file: Path,
    repo_root: Path,
    topic: str,
    content: str,
    source: str,
    confidence: float,
    tags: List[str],
    evidence: Optional[str],
    kind: Optional[str],
    allow_duplicate: bool,
    dry_run: bool,
) -> Dict[str, Any]:
    topic_name = ensure_topic_name(topic)
    normalized_content = ensure_content(content)
    normalized_source = ensure_source(source)
    normalized_confidence = ensure_confidence(confidence)
    normalized_tags = normalize_tags(tags)
    normalized_kind = normalize_kind(kind)
    normalized_evidence = evidence.strip() if evidence else None

    entries = store["topics"].setdefault(topic_name, [])
    candidate_key = normalized_content_key(normalized_content)
    if not allow_duplicate:
        for existing_entry in entries:
            if existing_entry["status"] != ACTIVE_STATUS:
                continue
            if normalized_content_key(existing_entry["content"]) == candidate_key:
                return {
                    "command": "write",
                    "schema_version": SCHEMA_VERSION,
                    "memory_file": str(memory_file),
                    "repo_root": str(repo_root),
                    "created": False,
                    "topic": topic_name,
                    "entry": existing_entry,
                    "reason": "duplicate_active_entry",
                }

    next_id = max((entry["id"] for entry in entries), default=0) + 1
    entry = {
        "id": next_id,
        "status": ACTIVE_STATUS,
        "created_at": utc_now(),
        "source": normalized_source,
        "confidence": normalized_confidence,
        "content": normalized_content,
        "tags": normalized_tags,
    }
    if normalized_kind:
        entry["kind"] = normalized_kind
    if normalized_evidence:
        entry["evidence"] = normalized_evidence

    if not dry_run:
        entries.append(entry)
        save_store(memory_file, store)

    return {
        "command": "write",
        "schema_version": SCHEMA_VERSION,
        "memory_file": str(memory_file),
        "repo_root": str(repo_root),
        "created": True,
        "topic": topic_name,
        "entry": entry,
        "dry_run": dry_run,
    }


def deprecate_entry(
    store: Dict[str, Any],
    memory_file: Path,
    repo_root: Path,
    topic: str,
    entry_id: int,
    reason: Optional[str],
    dry_run: bool,
) -> Dict[str, Any]:
    topic_name = ensure_topic_name(topic)
    entries = store["topics"].get(topic_name)
    if not entries:
        raise MissingEntryError(f"Topic '{topic_name}' was not found.")

    for entry in entries:
        if entry["id"] != entry_id:
            continue
        updated_entry = dict(entry)
        if updated_entry["status"] == DEPRECATED_STATUS:
            return {
                "command": "deprecate",
                "schema_version": SCHEMA_VERSION,
                "memory_file": str(memory_file),
                "repo_root": str(repo_root),
                "updated": False,
                "topic": topic_name,
                "entry": updated_entry,
                "reason": "already_deprecated",
            }

        updated_entry["status"] = DEPRECATED_STATUS
        updated_entry["deprecated_at"] = utc_now()
        if reason:
            updated_entry["deprecation_reason"] = reason.strip()

        if not dry_run:
            entries[entries.index(entry)] = updated_entry
            save_store(memory_file, store)

        return {
            "command": "deprecate",
            "schema_version": SCHEMA_VERSION,
            "memory_file": str(memory_file),
            "repo_root": str(repo_root),
            "updated": True,
            "topic": topic_name,
            "entry": updated_entry,
            "dry_run": dry_run,
        }

    raise MissingEntryError(f"Entry id {entry_id} was not found in topic '{topic_name}'.")


def validate_store(store: Dict[str, Any], memory_file: Path, repo_root: Path) -> Dict[str, Any]:
    issues: List[Dict[str, str]] = []
    for topic, entries in store["topics"].items():
        seen_ids = set()
        seen_content = set()
        for entry in entries:
            entry_id = entry["id"]
            if entry_id in seen_ids:
                issues.append(
                    {
                        "severity": "error",
                        "topic": topic,
                        "entry_id": str(entry_id),
                        "message": f"Duplicate entry id {entry_id} found in topic '{topic}'.",
                    }
                )
            seen_ids.add(entry_id)

            if entry["status"] == ACTIVE_STATUS:
                content_key = normalized_content_key(entry["content"])
                if content_key in seen_content:
                    issues.append(
                        {
                            "severity": "warning",
                            "topic": topic,
                            "entry_id": str(entry_id),
                            "message": f"Topic '{topic}' contains duplicate active content.",
                        }
                    )
                seen_content.add(content_key)

    return {
        "command": "validate",
        "schema_version": SCHEMA_VERSION,
        "memory_file": str(memory_file),
        "repo_root": str(repo_root),
        "valid": not any(issue["severity"] == "error" for issue in issues),
        "issues": issues,
        "stats": {
            "topics": len(store["topics"]),
            "entries": sum(len(entries) for entries in store["topics"].values()),
        },
    }


def emit_result(result: Dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    print(result)


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--memory-file", help="Override the project-memory file path.")
    common.add_argument("--repo-root", help="Override the repository root used for default path resolution.")
    common.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
        help="Choose stdout format. JSON is the default.",
    )

    parser = argparse.ArgumentParser(description="Manage project-local routing memory.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-topics", parents=[common], help="List known project-memory topics.")

    search_parser = subparsers.add_parser("search", parents=[common], help="Search project-memory entries.")
    search_parser.add_argument("--query", required=True, help="Case-insensitive search string.")
    search_parser.add_argument("--include-deprecated", action="store_true", help="Include deprecated entries in results.")
    search_parser.add_argument("--limit", type=int, default=20, help="Maximum number of matches to return.")

    read_parser = subparsers.add_parser("read", parents=[common], help="Read all entries for a topic.")
    read_parser.add_argument("--topic", required=True, help="Topic to read.")
    read_parser.add_argument("--include-deprecated", action="store_true", help="Include deprecated entries in output.")

    write_parser = subparsers.add_parser("write", parents=[common], help="Write a new project-memory entry.")
    write_parser.add_argument("--topic", required=True, help="Topic to append to.")
    write_parser.add_argument("--content", required=True, help="Project-memory statement.")
    write_parser.add_argument("--source", required=True, help="Who is writing the entry.")
    write_parser.add_argument("--confidence", type=float, default=1.0, help="Confidence score between 0.0 and 1.0.")
    write_parser.add_argument("--tags", default="", help="Optional comma-separated tags.")
    write_parser.add_argument("--evidence", help="Optional audit note.")
    write_parser.add_argument("--kind", help="Optional entry kind.")
    write_parser.add_argument("--allow-duplicate", action="store_true", help="Allow an exact active duplicate inside the same topic.")
    write_parser.add_argument("--dry-run", action="store_true", help="Return the proposed entry without writing it.")

    deprecate_parser = subparsers.add_parser("deprecate", parents=[common], help="Deprecate an existing entry instead of deleting it.")
    deprecate_parser.add_argument("--topic", required=True, help="Topic containing the entry.")
    deprecate_parser.add_argument("--id", required=True, type=int, help="Entry id within the topic.")
    deprecate_parser.add_argument("--reason", help="Optional audit reason for deprecation.")
    deprecate_parser.add_argument("--dry-run", action="store_true", help="Return the proposed deprecation without writing it.")

    subparsers.add_parser("validate", parents=[common], help="Validate the project-memory store shape.")
    return parser


def run_command(args: argparse.Namespace) -> Dict[str, Any]:
    repo_root = resolve_repo_root(args.repo_root)
    memory_file = resolve_memory_file(args.memory_file, repo_root)
    store = load_store(memory_file, repo_root)

    if args.command == "list-topics":
        return list_topics(store, memory_file, repo_root)
    if args.command == "search":
        if args.limit <= 0:
            raise InputValidationError("--limit must be a positive integer.")
        return search_entries(
            store=store,
            memory_file=memory_file,
            repo_root=repo_root,
            query=args.query,
            include_deprecated=args.include_deprecated,
            limit=args.limit,
        )
    if args.command == "read":
        return read_topic(
            store=store,
            memory_file=memory_file,
            repo_root=repo_root,
            topic=args.topic,
            include_deprecated=args.include_deprecated,
        )
    if args.command == "write":
        return write_entry(
            store=store,
            memory_file=memory_file,
            repo_root=repo_root,
            topic=args.topic,
            content=args.content,
            source=args.source,
            confidence=args.confidence,
            tags=args.tags,
            evidence=args.evidence,
            kind=args.kind,
            allow_duplicate=args.allow_duplicate,
            dry_run=args.dry_run,
        )
    if args.command == "deprecate":
        return deprecate_entry(
            store=store,
            memory_file=memory_file,
            repo_root=repo_root,
            topic=args.topic,
            entry_id=args.id,
            reason=args.reason,
            dry_run=args.dry_run,
        )
    if args.command == "validate":
        return validate_store(store, memory_file, repo_root)
    raise InputValidationError(f"Unsupported command '{args.command}'.")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        emit_result(run_command(args), args.format)
        return 0
    except ProjectMemoryError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return exc.exit_code
    except Exception as exc:  # pragma: no cover - defensive safeguard
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
