import datetime
import json
import os
import sys
from pathlib import Path


LIST_FIELDS = {
    "tags",
    "capabilities",
    "accepted_intents",
    "input_artifacts",
    "output_artifacts",
    "stack_tags",
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
}


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


def normalize_metadata(frontmatter, folder_name="unknown"):
    metadata = dict(frontmatter)
    
    # Load Semantic AI Manifest for intelligent enrichment
    manifest_path = Path(__file__).parent.parent / "config" / "skill_enrichments.json"
    manifest = {}
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            pass

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
    enrichment = manifest.get(folder_name) or manifest.get(name)
    
    if is_empty and enrichment:
        fields_to_enrich = ["capabilities", "accepted_intents", "stack_tags", "tags", "input_artifacts", "output_artifacts"]
        
        metadata["enrichment_count"] = 0
        for field in fields_to_enrich:
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


def find_skills(scan_dirs):
    """Discover and normalize skills from the provided directories."""
    skills = {}
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
                    frontmatter = parse_frontmatter(content)
                    name = frontmatter.get("name") or folder.name

                    if name == "skill-dispatcher":
                        continue

                    if not frontmatter.get("description"):
                        print(f" [!] Warning: Skill '{name}' in {folder.name} is missing a description.")

                    if name in skills:
                        print(f" [!] Skipping duplicate skill: {name} (keeping {skills[name]['path']})")
                        continue

                    metadata = normalize_metadata(frontmatter, folder.name)

                    skills[name] = {
                        "name": name,
                        "metadata": metadata,
                        "path": str(folder.resolve()),
                        "source": str(directory.resolve()),
                    }
                except Exception as error:
                    print(f" [!] Error parsing skill in {folder}: {error}")
        except Exception as error:
            print(f" [!] Error accessing directory {directory}: {error}")

    return skills


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
                "writes_files": metadata.get("writes_files", False),
                "manual_only": metadata.get("manual_only", False),
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
    print("=== AgentSkill Registry Builder ===")

    current_script = Path(__file__).resolve()
    skill_root = current_script.parent.parent
    registry_dir = skill_root / "registry"
    markdown_path = registry_dir / "SKILL_REGISTRY.md"
    json_path = registry_dir / "SKILL_REGISTRY.json"

    scan_dirs = candidate_scan_dirs(skill_root)
    skills = find_skills(scan_dirs)
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
        markdown_path.write_text(markdown, encoding="utf-8")
        json_path.write_text(json.dumps(json_registry, indent=2) + "\n", encoding="utf-8")
        print(f"[*] Successfully built registry at: {markdown_path}")
        print(f"[*] Machine-readable registry written to: {json_path}")
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


if __name__ == "__main__":
    main()
