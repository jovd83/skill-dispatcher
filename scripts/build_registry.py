import argparse
import subprocess
import datetime
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Optional: import normalize() from skill-yaml-cleanup if available.
# build_registry uses it for --preflight in-memory normalization.
# Falls back to a no-op so the registry can still be built without the
# cleanup skill installed.
# ---------------------------------------------------------------------------
def _try_import_normalize():
    """Return the normalize() callable from _common, or None if unavailable."""
    # Common locations relative to this script's parent (skill-dispatcher root)
    skill_root = Path(__file__).parent.parent
    candidates = [
        skill_root.parent / "Skill-yaml-cleanup" / "scripts",
        skill_root.parent / "skill-yaml-cleanup" / "scripts",
        Path.home() / ".agents" / "skills" / "skill-yaml-cleanup" / "scripts",
        Path.home() / ".agents" / "skills" / "Skill-yaml-cleanup" / "scripts",
    ]
    for candidate in candidates:
        if (candidate / "_common.py").exists():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            try:
                from _common import normalize  # noqa: PLC0415
                return normalize
            except ImportError:
                pass
    return None


LIST_FIELDS = {
    "tags",
    "capabilities",
    "accepted_intents",
    "input_artifacts",
    "output_artifacts",
    "stack_tags",
    "downstream_skills",
}

BOOL_FIELDS = {"writes_files", "manual_only"}

DISPATCHER_METADATA_KEYS = {
    "category": "dispatcher-category",
    "capabilities": "dispatcher-capabilities",
    "accepted_intents": "dispatcher-accepted-intents",
    "input_artifacts": "dispatcher-input-artifacts",
    "output_artifacts": "dispatcher-output-artifacts",
    "stack_tags": "dispatcher-stack-tags",
    "risk": "dispatcher-risk",
    "writes_files": "dispatcher-writes-files",
    "manual_only": "dispatcher-manual-only",
    "layer": "dispatcher-layer",
    "lifecycle": "dispatcher-lifecycle",
    "downstream_skills": "dispatcher-downstream-skills",
    "preferred_model": "dispatcher-preferred-model",
}

ENRICHMENT_FIELDS = [
    "capabilities",
    "accepted_intents",
    "stack_tags",
    "tags",
    "input_artifacts",
    "output_artifacts",
]


def load_json_file(path):
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def merge_unique_lists(*values):
    merged = []
    seen = set()
    for value in values:
        for item in normalize_list(value):
            if item not in seen:
                seen.add(item)
                merged.append(item)
    return merged


def parse_scalar(value):
    """Parse a simple YAML scalar without external dependencies."""
    clean = value.strip()
    if not clean:
        return ""

    lower = clean.lower()
    if lower in ("true", "yes", "on"):
        return True
    if lower in ("false", "no", "off"):
        return False
    if clean.startswith("[") and clean.endswith("]"):
        inner = clean[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip("'").strip('"') for item in inner.split(",")]

    return clean.strip("'").strip('"')


def parse_frontmatter(content):
    """
    Parse YAML-like frontmatter for AgentSkills.
    Supports:
    - single-line scalars
    - inline lists
    - indented bullet lists
    - simple multiline scalars
    """
    if not content.startswith("---"):
        return {}

    lines = content.splitlines()
    end_index = -1
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = i
            break

    if end_index == -1:
        return {}

    metadata = {}
    current_key = None
    current_mode = None

    for raw_line in lines[1:end_index]:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip(" \t"))

        if indent == 0 and ":" in line:
            key, raw_value = line.split(":", 1)
            current_key = key.strip()
            value = raw_value.strip()

            if value in ("|", "|-", ">", ">-"):
                metadata[current_key] = ""
                current_mode = "multiline"
            elif value == "":
                metadata[current_key] = None
                current_mode = "pending"
            else:
                metadata[current_key] = parse_scalar(value)
                current_mode = "scalar"
            continue

        if current_key is None or indent == 0:
            continue

        if stripped.startswith("- "):
            item = parse_scalar(stripped[2:].strip())
            existing = metadata.get(current_key)
            if existing is None:
                metadata[current_key] = []
            elif not isinstance(existing, list):
                metadata[current_key] = [existing]
            metadata[current_key].append(item)
            current_mode = "list"
            continue

        if ":" in stripped and current_mode in ("pending", "mapping"):
            nested_key, nested_raw_value = stripped.split(":", 1)
            nested_value = parse_scalar(nested_raw_value.strip())
            existing = metadata.get(current_key)
            if existing is None:
                metadata[current_key] = {}
                existing = metadata[current_key]
            if not isinstance(existing, dict):
                metadata[current_key] = {}
                existing = metadata[current_key]
            existing[nested_key.strip()] = nested_value
            current_mode = "mapping"
            continue

        if current_mode == "multiline":
            metadata[current_key] += stripped + "\n"
            continue

        existing = metadata.get(current_key)
        if existing is None:
            metadata[current_key] = stripped
        elif isinstance(existing, str):
            metadata[current_key] += " " + stripped

    cleaned = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, str):
            cleaned[key] = value.strip()
        else:
            cleaned[key] = value
    return cleaned


def normalize_category(value):
    if not isinstance(value, str):
        return "uncategorized"

    clean = value.lower().strip()
    if any(word in clean for word in ("test", "qa", "automation", "coverage")):
        return "testing"
    if any(word in clean for word in ("sec", "audit", "vuln", "protection")):
        return "security"
    if any(word in clean for word in ("analyze", "req", "feat", "planning")):
        return "analysis"
    if any(word in clean for word in ("dev", "ops", "deploy", "infra")):
        return "infrastructure"
    return clean or "uncategorized"


def normalize_risk(value):
    if not isinstance(value, str):
        return "medium"

    clean = value.lower().strip()
    if any(word in clean for word in ("high", "critical", "extreme", "3")):
        return "high"
    if any(word in clean for word in ("low", "minimal", "1")):
        return "low"
    return "medium"


def normalize_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        if not value.strip():
            return []
        if "," in value:
            return [item.strip() for item in value.split(",") if item.strip()]
        return [value.strip()]
    return [str(value).strip()]


def normalize_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower().strip() in ("true", "yes", "on", "1")
    return False


def normalize_layer(metadata, name, folder_name):
    """Semantic heuristic to infer the architectural layer if missing."""
    value = metadata.get("layer")
    if value:
        return value.lower().strip()

    # Keywords for scoring
    info_keys = {"context", "index", "documentation", "discovery", "glossary", "metadata", "memory", "research", "loading", "portfolio"}
    feedback_keys = {"audit", "review", "critique", "security", "checker", "inspector", "guard", "monitor", "eval", "qa", "verification", "assessment"}
    
    score_info = 0
    score_feedback = 0
    
    # Check Name/Folder
    id_text = f"{name} {folder_name}".lower()
    for k in info_keys:
        if k in id_text: score_info += 2
    for k in feedback_keys:
        if k in id_text: score_feedback += 2
        
    # Check Description
    desc = metadata.get("description", "").lower()
    for k in info_keys:
        if k in desc: score_info += 1
    for k in feedback_keys:
        if k in desc: score_feedback += 1
        
    # Check Category
    cat = metadata.get("category", "").lower()
    if cat == "testing": score_feedback += 2
    if cat == "security": score_feedback += 3
    if cat == "analysis": score_info += 1
    
    # Check Capabilities/Intents
    actions = " ".join(metadata.get("capabilities", []) + metadata.get("accepted_intents", [])).lower()
    for k in info_keys:
        if k in actions: score_info += 1
    for k in feedback_keys:
        if k in actions: score_feedback += 1

    if score_feedback > score_info and score_feedback > 0:
        return "feedback"
    if score_info > 0:
        return "information"
        
    return "execution" # Standard default


def normalize_lifecycle(value):
    if not isinstance(value, str):
        return "active"
    clean = value.lower().strip()
    if clean in ("active", "sunset", "archived"):
        return clean
    return "active"


def normalize_metadata(frontmatter, folder_name="unknown", enrichment_manifest=None, relationship_manifest=None):
    metadata = dict(frontmatter)

    metadata_block = metadata.get("metadata", {})
    if not isinstance(metadata_block, dict):
        metadata_block = {}

    for field, metadata_key in DISPATCHER_METADATA_KEYS.items():
        if field not in metadata and metadata_key in metadata_block:
            metadata[field] = metadata_block[metadata_key]

    # Semantic AI Enrichment for empty fields
    name = metadata.get("name") or folder_name
    
    # Check if critical fields are empty
    is_empty = not any([
        metadata.get("capabilities"),
        metadata.get("accepted_intents"),
        metadata.get("tags")
    ])
    
    # Prioritize Folder Name lookup in AI Manifest
    enrichment_manifest = enrichment_manifest or {}
    relationship_manifest = relationship_manifest or {}

    enrichment = enrichment_manifest.get(folder_name) or enrichment_manifest.get(name)
    
    if is_empty and enrichment:
        metadata["enrichment_count"] = 0
        for field in ENRICHMENT_FIELDS:
            if not metadata.get(field) and enrichment.get(field):
                metadata[field] = enrichment.get(field)
                metadata["enrichment_count"] += len(enrichment.get(field))
        
        # Category is a special scalar
        if not metadata.get("category") and enrichment.get("category"):
            metadata["category"] = enrichment.get("category")
    else:
        metadata["enrichment_count"] = 0

    metadata["category"] = normalize_category(metadata.get("category"))
    metadata["risk"] = normalize_risk(metadata.get("risk"))

    for field in LIST_FIELDS:
        metadata[field] = normalize_list(metadata.get(field))

    for field in BOOL_FIELDS:
        metadata[field] = normalize_bool(metadata.get(field))

    relationship_overlay = relationship_manifest.get(folder_name) or relationship_manifest.get(name) or {}
    metadata["downstream_skills"] = merge_unique_lists(
        relationship_overlay.get("downstream_skills"),
        metadata.get("downstream_skills"),
    )

    # New: Layer & Lifecycle Inference
    metadata["layer"] = normalize_layer(metadata, name, folder_name)
    metadata["lifecycle"] = normalize_lifecycle(metadata.get("lifecycle"))

    return metadata


def candidate_scan_dirs(skill_root):
    """Build the ordered list of directories to scan."""
    repo_root = skill_root.parent.parent
    local_skills_dir = repo_root / "skills"
    global_agent_skills = Path.home() / ".agents" / "skills"
    extra_dirs = os.environ.get("SKILL_DISPATCHER_EXTRA_DIRS", "")

    raw_dirs = []

    if local_skills_dir.exists() and local_skills_dir.is_dir():
        raw_dirs.append(local_skills_dir)

    if skill_root.parent and skill_root.parent != skill_root:
        raw_dirs.append(skill_root.parent)

    if repo_root.parent and repo_root.parent.name == "skills":
        raw_dirs.append(repo_root.parent)

    if global_agent_skills.exists() and global_agent_skills.is_dir():
        raw_dirs.append(global_agent_skills)

    for extra_dir in extra_dirs.split(os.pathsep):
        if extra_dir.strip():
            raw_dirs.append(Path(extra_dir.strip()))

    ordered = []
    seen = set()
    for directory in raw_dirs:
        resolved = str(Path(directory).resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        ordered.append(Path(resolved))
    return ordered


def build_indexes(skills):
    capability_index = {}
    intent_index = {}

    for name, data in skills.items():
        metadata = data["metadata"]
        for capability in metadata.get("capabilities", []):
            capability_index.setdefault(capability, []).append(name)
        for intent in metadata.get("accepted_intents", []):
            intent_index.setdefault(intent, []).append(name)

    for index in (capability_index, intent_index):
        for key in index:
            index[key] = sorted(index[key])

    return capability_index, intent_index


def diff_registries(prev_payload: dict, new_payload: dict) -> dict:
    """Compute additions, removals, and metadata changes between two registries.

    Both payloads are full SKILL_REGISTRY.json dicts. Skills can live as either
    a list under `skills` or a dict — this handles both shapes.
    Returns a dict suitable for one JSONL row of registry_history.jsonl.
    """
    def _extract(payload):
        raw = (payload or {}).get("skills", {})
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, list):
            return {item.get("name"): item for item in raw if isinstance(item, dict) and item.get("name")}
        return {}

    prev = _extract(prev_payload)
    new = _extract(new_payload)
    prev_names = set(prev)
    new_names = set(new)

    added = sorted(new_names - prev_names)
    removed = sorted(prev_names - new_names)

    # Detect metadata-shape changes for skills present in both snapshots
    tracked_fields = ("layer", "category", "risk", "lifecycle", "writes_files")
    changed = {}
    for name in sorted(prev_names & new_names):
        before = prev.get(name, {})
        after = new.get(name, {})
        diffs = {}
        for field in tracked_fields:
            b = before.get(field)
            a = after.get(field)
            if b != a:
                diffs[field] = {"from": b, "to": a}
        if diffs:
            changed[name] = diffs

    return {
        "prev_count": len(prev_names),
        "new_count": len(new_names),
        "added": added,
        "removed": removed,
        "changed": changed,
    }




def _is_chain_candidate(folder: Path, content: str, metadata: dict) -> bool:
    """Return True if this skill looks like a multi-phase chain with no chain_definition.json yet."""
    if (folder / "config" / "chain_definition.json").exists():
        return False
    if metadata.get("risk", "") != "high":
        return False
    # Body is everything after the closing frontmatter delimiter
    fm_end = content.find("\n---", 3)
    body = content[fm_end:] if fm_end > 0 else content
    body_lower = body.lower()
    # Count how many phase/orchestration signals appear in the body
    signals = [
        "### ", "phase 0", "phase 1", "## workflow", "## phase",
        "lifecycle", "orchestrat", "coordinates", "end-to-end", "sdlc",
    ]
    hits = sum(1 for s in signals if s in body_lower)
    return hits >= 2

def find_skills(scan_dirs, *, preflight_fn=None, strict=False):
    """Discover and normalize skills from the provided directories.

    Args:
        scan_dirs: ordered list of directories to scan.
        preflight_fn: optional callable(fm_text) -> (fm_text, report).
            When provided, each SKILL.md's raw frontmatter is normalized
            in memory before parsing.  Issues are logged and collected into
            the returned health_report dict.
        strict: if True, sys.exit(1) when any skill is oversized after
            normalization.  Defaults to False (lenient — warns but continues).

    Returns:
        (skills dict, health_report dict)
    """
    skills = {}
    health_report = {}
    config_dir = Path(__file__).parent.parent / "config"
    enrichment_manifest = load_json_file(config_dir / "skill_enrichments.json")
    relationship_manifest = load_json_file(config_dir / "skill_relationships.json")
    print("[*] Scanning for skills in: " + ", ".join(str(directory) for directory in scan_dirs))

    for directory in scan_dirs:
        if not directory.exists() or not directory.is_dir():
            continue

        try:
            for folder in sorted(directory.iterdir(), key=lambda path: path.name.lower()):
                if not folder.is_dir() or folder.name.startswith("."):
                    continue

                skill_file = folder / "SKILL.md"
                if not skill_file.exists():
                    continue

                try:
                    content = skill_file.read_text(encoding="utf-8")

                    # --- Preflight normalization (in-memory, never writes) ---
                    if preflight_fn is not None:
                        fm_start = content.find("\n", 3) + 1  # skip opening ---
                        fm_end = content.find("\n---", fm_start)
                        if fm_start > 0 and fm_end > fm_start:
                            raw_fm = content[fm_start:fm_end]
                            norm_fm, report = preflight_fn(raw_fm)
                            skill_key = str(skill_file)
                            issues = []
                            if report.get("dedupe_removed", 0) > 0:
                                issues.append(f"duplicate_metadata_blocks:{report['dedupe_removed']}_lines_removed")
                            if report.get("flattened_fields"):
                                issues.append(f"vertical_lists:{','.join(report['flattened_fields'])}")
                            if report.get("noise_stripped"):
                                issues.append(f"noise_fields:{','.join(report['noise_stripped'])}")
                            if report.get("oversized"):
                                issues.append(f"oversized:{report['char_count']}_chars")
                                if strict:
                                    print(f" [!] STRICT: {skill_file} frontmatter is {report['char_count']} chars (limit 1000). Aborting.")
                                    sys.exit(1)
                                else:
                                    print(f" [!] Warning: {folder.name} frontmatter is {report['char_count']} chars (limit 1000).")
                            if issues:
                                health_report[skill_key] = {"skill": folder.name, "issues": issues, "char_count": report.get("char_count", 0)}
                                print(f" [~] Preflight normalized {folder.name}: {'; '.join(issues)}")
                            # Rebuild content with normalized frontmatter for parsing
                            content = content[:fm_start] + norm_fm + content[fm_end:]
                    # ---------------------------------------------------------

                    frontmatter = parse_frontmatter(content)
                    name = frontmatter.get("name") or folder.name

                    if name == "skill-dispatcher":
                        continue

                    # Name-drift check: registry key (frontmatter name) must equal install directory name.
                    # Drift causes silent failures when the orchestrator resolves SKILL.md paths by dir name.
                    if frontmatter.get("name") and frontmatter.get("name") != folder.name:
                        drift_msg = f"name_drift:{frontmatter['name']}!={folder.name}"
                        print(f" [!] Name drift in {folder.name}: SKILL.md 'name: {frontmatter['name']}' != dir '{folder.name}'")
                        skill_key = str(skill_file)
                        if skill_key not in health_report:
                            health_report[skill_key] = {"skill": folder.name, "issues": [], "char_count": 0}
                        if drift_msg not in health_report[skill_key]["issues"]:
                            health_report[skill_key]["issues"].append(drift_msg)

                    if not frontmatter.get("description"):
                        print(f" [!] Warning: Skill '{name}' in {folder.name} is missing a description.")

                    if name in skills:
                        print(f" [!] Skipping duplicate skill: {name} (keeping {skills[name]['path']})")
                        continue

                    metadata = normalize_metadata(
                        frontmatter,
                        folder.name,
                        enrichment_manifest=enrichment_manifest,
                        relationship_manifest=relationship_manifest,
                    )

                    skills[name] = {
                        "name": name,
                        "metadata": metadata,
                        "path": str(folder.resolve()),
                        "source": str(directory.resolve()),
                    }
                    # Chain-candidate detection: flag skills that look like multi-phase
                    # orchestrators but have no chain_definition.json yet.
                    if _is_chain_candidate(folder, content, metadata):
                        skill_key = str(skill_file)
                        if skill_key not in health_report:
                            health_report[skill_key] = {"skill": folder.name, "issues": [], "char_count": 0}
                        if "missing_chain_definition" not in health_report[skill_key]["issues"]:
                            health_report[skill_key]["issues"].append("missing_chain_definition")
                            print(f" [*] Chain candidate: {folder.name} (no chain_definition.json)")


                except Exception as error:
                    print(f" [!] Error parsing skill in {folder}: {error}")
        except Exception as error:
            print(f" [!] Error accessing directory {directory}: {error}")

    return skills, health_report


def render_markdown_registry(skills, scan_dirs, generated_at, capability_index, intent_index):
    by_category = {}
    for name, data in skills.items():
        category = data["metadata"].get("category", "uncategorized")
        by_category.setdefault(category, []).append((name, data))

    lines = [
        "# Skill Registry",
        "",
        f"This registry was automatically generated on **{generated_at.strftime('%Y-%m-%d %H:%M:%S')}**.",
        f"Total active skills: **{len(skills)}**",
        "",
        "## Dispatch Contract Snapshot",
        "",
        "- `intent`: normalized routing intent for the current step",
        "- `current_artifact_type`: artifact currently available to the next skill",
        "- `target_artifact_type`: artifact expected from the next skill",
        "- `repo_context`: relevant repository evidence, stack, and conventions",
        "- `constraints`: policy, safety, and delivery constraints",
        "- `preferred_stack`: preferred framework when already known",
        "- `allowed_write_risk`: `low`, `medium`, or `high`",
        "",
        "The machine-readable source of truth for this registry is `SKILL_REGISTRY.json`.",
        "",
        "## Indexed Scan Directories",
        "",
    ]

    for directory in scan_dirs:
        lines.append(f"- `{directory}`")

    if capability_index:
        lines.extend(["", "## Capability Index", ""])
        for capability in sorted(capability_index):
            lines.append(f"- `{capability}`: {', '.join(f'`{name}`' for name in capability_index[capability])}")

    if intent_index:
        lines.extend(["", "## Intent Index", ""])
        for intent in sorted(intent_index):
            lines.append(f"- `{intent}`: {', '.join(f'`{name}`' for name in intent_index[intent])}")

    lines.extend(["", "---", ""])

    for category in sorted(by_category):
        lines.append(f"## Category: {category.upper()}")
        for name, data in sorted(by_category[category], key=lambda item: item[0].lower()):
            metadata = data["metadata"]
            lines.append(f"### `{name}`")
            lines.append(f"- **Description**: {metadata.get('description', '*No description provided.*')}")

            for field, label in (
                ("capabilities", "Capabilities"),
                ("accepted_intents", "Accepted intents"),
                ("input_artifacts", "Input artifacts"),
                ("output_artifacts", "Output artifacts"),
                ("stack_tags", "Stack tags"),
                ("downstream_skills", "Declared downstream skills"),
                ("tags", "Tags"),
            ):
                values = metadata.get(field, [])
                if values:
                    lines.append(f"- **{label}**: `{', '.join(values)}`")

            lines.append(f"- **Risk**: `{metadata.get('risk', 'medium')}`")
            lines.append(f"- **Layer**: `{metadata.get('layer', 'execution')}`")
            lines.append(f"- **Lifecycle**: `{metadata.get('lifecycle', 'active')}`")
            lines.append(f"- **Writes files**: `{str(metadata.get('writes_files', False)).lower()}`")
            lines.append(f"- **Manual only**: `{str(metadata.get('manual_only', False)).lower()}`")
            lines.append("- **Telemetry**: `required` (via Skill Dispatcher)")
            lines.append(f"- **Location**: `{data['path']}`")
            lines.append("")

    return "\n".join(lines)


def render_json_registry(skills, scan_dirs, generated_at, capability_index, intent_index):
    skill_entries = []
    for name in sorted(skills):
        data = skills[name]
        metadata = data["metadata"]
        skill_entries.append(
            {
                "name": name,
                "description": metadata.get("description", ""),
                "category": metadata.get("category", "uncategorized"),
                "risk": metadata.get("risk", "medium"),
                "layer": metadata.get("layer", "execution"),
                "lifecycle": metadata.get("lifecycle", "active"),
                "tags": metadata.get("tags", []),
                "capabilities": metadata.get("capabilities", []),
                "accepted_intents": metadata.get("accepted_intents", []),
                "input_artifacts": metadata.get("input_artifacts", []),
                "output_artifacts": metadata.get("output_artifacts", []),
                "stack_tags": metadata.get("stack_tags", []),
                "downstream_skills": metadata.get("downstream_skills", []),
                "writes_files": metadata.get("writes_files", False),
                "manual_only": metadata.get("manual_only", False),
                "preferred_model": metadata.get("preferred_model", ""),
                "telemetry": "required",
                "location": data["path"],
                "source": data["source"],
            }
        )

    return {
        "generated_at": generated_at.isoformat(),
        "registry_contract_version": "2.0",
        "dispatch_contract": {
            "inputs": [
                "intent",
                "current_artifact_type",
                "target_artifact_type",
                "repo_context",
                "constraints",
                "preferred_stack",
                "allowed_write_risk",
            ],
            "outputs": ["decision", "selected_skill", "reason", "handoff_payload"],
        },
        "scan_directories": [str(directory) for directory in scan_dirs],
        "capability_index": capability_index,
        "intent_index": intent_index,
        "skills": skill_entries,
    }


def main():
    parser = argparse.ArgumentParser(description="AgentSkill Registry Builder")
    parser.add_argument(
        "--preflight",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Normalize SKILL.md frontmatter in memory before parsing (default: on). "
             "Requires skill-yaml-cleanup to be installed alongside this skill.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Fail with exit code 1 if any skill has oversized frontmatter after normalization.",
    )
    args = parser.parse_args()

    print("=== AgentSkill Registry Builder ===")

    current_script = Path(__file__).resolve()
    skill_root = current_script.parent.parent

    # SAFE ZONE Priority: survive 'npx skills add' updates
    persistent_base = Path.home() / ".agents" / "dispatcher-data"

    if ".agents" in str(skill_root.resolve()).lower():
        registry_dir = persistent_base / "registry"
    else:
        registry_dir = skill_root / "registry"

    markdown_path = registry_dir / "SKILL_REGISTRY.md"
    json_path = registry_dir / "SKILL_REGISTRY.json"
    health_path = registry_dir / "registry_health.json"
    history_path = registry_dir / "registry_history.jsonl"

    # Resolve preflight normalizer
    preflight_fn = None
    if args.preflight:
        preflight_fn = _try_import_normalize()
        if preflight_fn is None:
            print("[~] Preflight: skill-yaml-cleanup not found — skipping in-memory normalization.")
        else:
            print("[*] Preflight: normalize() loaded from skill-yaml-cleanup.")

    scan_dirs = candidate_scan_dirs(skill_root)
    skills, health_report = find_skills(scan_dirs, preflight_fn=preflight_fn, strict=args.strict)
    generated_at = datetime.datetime.now()

    if not skills:
        print("[*] No additional skills discovered.")
        registry_dir.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(
            "# Skill Registry\n\n"
            f"*Last updated: {generated_at.isoformat()}*\n\n"
            "No skills discovered yet.",
            encoding="utf-8",
        )
        json_path.write_text(
            json.dumps(
                {
                    "generated_at": generated_at.isoformat(),
                    "registry_contract_version": "2.0",
                    "skills": [],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return

    capability_index, intent_index = build_indexes(skills)
    markdown = render_markdown_registry(skills, scan_dirs, generated_at, capability_index, intent_index)
    json_registry = render_json_registry(skills, scan_dirs, generated_at, capability_index, intent_index)

    try:
        registry_dir.mkdir(parents=True, exist_ok=True)

        # Read previous registry (before overwriting) so we can diff
        prev_payload = load_json_file(json_path)

        markdown_path.write_text(markdown, encoding="utf-8")
        json_path.write_text(json.dumps(json_registry, indent=2) + "\n", encoding="utf-8")
        health_payload = {
            "generated_at": generated_at.isoformat(),
            "preflight_enabled": preflight_fn is not None,
            "skills_with_issues": len(health_report),
            "issues": health_report,
        }
        health_path.write_text(json.dumps(health_payload, indent=2) + "\n", encoding="utf-8")

        # Append a registry-history entry only when something actually changed.
        if prev_payload:
            diff = diff_registries(prev_payload, json_registry)
            if diff["added"] or diff["removed"] or diff["changed"]:
                history_entry = {
                    "timestamp": generated_at.isoformat(),
                    **diff,
                }
                with open(history_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(history_entry) + "\n")
                summary = (
                    f"+{len(diff['added'])} -{len(diff['removed'])} "
                    f"~{len(diff['changed'])}"
                )
                print(f"[*] Registry diff written ({summary}): {history_path}")

        print(f"[*] Successfully built registry at: {markdown_path}")
        print(f"[*] Machine-readable registry written to: {json_path}")
        if health_report:
            print(f"[~] Registry health report ({len(health_report)} issues): {health_path}")
        else:
            print(f"[*] Registry health: all skills clean — {health_path}")
    except Exception as error:
        print(f"[!] Critical Error: Failed to write registry: {error}")
        sys.exit(1)

    print("\n--- Discovery Summary ---")
    for name in sorted(skills):
        metadata = skills[name]["metadata"]
        category = metadata.get("category", "uncategorized")
        enrichment = metadata.get("enrichment_count", 0)
        enrich_star = f"(+{enrichment} tags inferred)" if enrichment > 0 else "(Manual)"
        print(f"[{category:^14}] {name:<35} {enrich_star}")
    print("--------------------------\n")

    # Auto-spawn propose_chains.py for any new chain candidates (non-blocking).
    candidates = [
        v["skill"] for v in health_report.values()
        if "missing_chain_definition" in v.get("issues", [])
    ]
    if candidates:
        proposer = Path(__file__).parent / "propose_chains.py"
        if proposer.exists():
            print(f"[*] Spawning propose_chains.py for {len(candidates)} candidate(s): {candidates}")
            subprocess.Popen(
                [sys.executable, str(proposer)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            print(f"[~] Chain candidates found but propose_chains.py not installed: {candidates}")


if __name__ == "__main__":
    main()
