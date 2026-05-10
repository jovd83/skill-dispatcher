#!/usr/bin/env python3
"""Add or remove the standard telemetry paragraph in SKILL.md files.

Optionally patch missing dispatcher tags in SKILL.md frontmatter.
"""

import argparse
import json
import re
from pathlib import Path

NOTICE = """## Telemetry & Logging
> [!IMPORTANT]
> All usage of this skill must be logged via the Skill Dispatcher to ensure audit logs and wallboard analytics are accurate:
> `./log-dispatch.cmd --skill <skill_name> --intent <intent> --model <model_name> --reason <reason>` (or `./log-dispatch.sh` on Linux)
"""

NOTICE_PATTERN = re.compile(
    r"\n*## Telemetry & Logging\s*\n"
    r"(?:>.*\n?)*"
    r"(?=\n## |\n# |\Z)",
    re.MULTILINE,
)

STANDARD_SCHEMA = [
    "dispatcher-category",
    "dispatcher-layer",
    "dispatcher-lifecycle",
    "dispatcher-risk",
    "dispatcher-writes-files",
    "dispatcher-capabilities",
    "dispatcher-accepted-intents",
    "dispatcher-input-artifacts",
    "dispatcher-output-artifacts",
    "dispatcher-stack-tags",
    "dispatcher-persistent-directories",
]

SCHEMA_MAPPING = {
    "dispatcher-capabilities": "capabilities",
    "dispatcher-accepted-intents": "accepted_intents",
    "dispatcher-input-artifacts": "input_artifacts",
    "dispatcher-output-artifacts": "output_artifacts",
    "dispatcher-stack-tags": "stack_tags",
    "dispatcher-persistent-directories": "persistent_directories",
}


def default_target() -> Path:
    return Path.home() / ".agents" / "skills"


def default_enrichments_path() -> Path:
    return Path(__file__).resolve().parent.parent / "config" / "skill_enrichments.json"


def find_skill_files(root_dir: Path):
    return sorted(root_dir.rglob("SKILL.md"))


def relative_label(path: Path, root_dir: Path) -> str:
    try:
        return str(path.relative_to(root_dir))
    except ValueError:
        return str(path)


def strip_notice(content: str) -> str:
    cleaned = NOTICE_PATTERN.sub("\n", content)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned + "\n" if cleaned else ""


def add_notice(content: str) -> str:
    body_without_notice = strip_notice(content)
    notice = NOTICE.strip()

    if body_without_notice.startswith("---\n"):
        closing = body_without_notice.find("\n---\n", 4)
        if closing != -1:
            frontmatter_end = closing + len("\n---\n")
            frontmatter = body_without_notice[:frontmatter_end].rstrip()
            body = body_without_notice[frontmatter_end:].strip()
            if body:
                return f"{frontmatter}\n\n{notice}\n\n{body}\n"
            return f"{frontmatter}\n\n{notice}\n"

    body = body_without_notice.strip()
    if body:
        return f"{notice}\n\n{body}\n"
    return f"{notice}\n"


def remove_notice(content: str) -> str:
    return strip_notice(content)


def yaml_scalar(value) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def yaml_csv(values) -> str:
    if not values:
        return ""
    if isinstance(values, list):
        return ", ".join(str(item) for item in values)
    return str(values)


def load_enrichments(path: Path):
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def patch_missing_dispatcher_tags(content: str, skill_name: str, enrichments: dict) -> str:
    frontmatter_match = re.match(r"^(---\s*\n)(.*?)(\n---\s*\n?)", content, re.DOTALL)
    if not frontmatter_match:
        return content

    prefix, frontmatter, suffix = frontmatter_match.groups()
    if "metadata:" not in frontmatter:
        frontmatter = frontmatter.rstrip() + "\nmetadata:\n"

    metadata_match = re.search(r"(^metadata:\s*\n)(.*)$", frontmatter, re.DOTALL | re.MULTILINE)
    if not metadata_match:
        return content

    metadata_header = metadata_match.group(1)
    metadata_body = metadata_match.group(2)
    enrichment = enrichments.get(skill_name, {})

    tag_lines = []

    def has_key(key: str) -> bool:
        return re.search(rf"^\s{{2}}{re.escape(key)}\s*:", metadata_body, re.MULTILINE) is not None

    if not has_key("dispatcher-category"):
        category = enrichment.get("category", enrichment.get("layer", "execution"))
        tag_lines.append(f"  dispatcher-category: {yaml_scalar(category)}")

    if not has_key("dispatcher-layer"):
        tag_lines.append(f"  dispatcher-layer: {yaml_scalar(enrichment.get('layer', 'execution'))}")

    if not has_key("dispatcher-lifecycle"):
        tag_lines.append("  dispatcher-lifecycle: active")

    if not has_key("dispatcher-risk"):
        tag_lines.append(f"  dispatcher-risk: {yaml_scalar(enrichment.get('risk', 'low'))}")

    if not has_key("dispatcher-writes-files"):
        writes_files = enrichment.get("writes_files", "false")
        tag_lines.append(f"  dispatcher-writes-files: {yaml_scalar(writes_files)}")

    for yaml_key, enrichment_key in SCHEMA_MAPPING.items():
        if has_key(yaml_key):
            continue
        value = yaml_csv(enrichment.get(enrichment_key, []))
        tag_lines.append(f"  {yaml_key}: {value}")

    if not tag_lines:
        return content

    injected_metadata = metadata_header + "\n".join(tag_lines) + "\n" + metadata_body.lstrip("\n")
    updated_frontmatter = frontmatter[: metadata_match.start()] + injected_metadata
    return prefix + updated_frontmatter.rstrip() + suffix + content[frontmatter_match.end() :]


def process_files(
    root_dir: Path,
    add_paragraph: bool,
    remove_paragraph: bool,
    write: bool,
    patch_missing_tags: bool,
    enrichments: dict,
) -> int:
    skill_files = find_skill_files(root_dir)
    print(f"[*] Searching in: {root_dir}")
    print(f"[*] Found {len(skill_files)} SKILL.md files.")

    changed_count = 0
    for skill_file in skill_files:
        original = skill_file.read_text(encoding="utf-8")
        updated = original

        if remove_paragraph:
            updated = remove_notice(updated)
        if add_paragraph:
            updated = add_notice(updated)

        if patch_missing_tags:
            updated = patch_missing_dispatcher_tags(updated, skill_file.parent.name.lower(), enrichments)

        if updated == original:
            continue

        changed_count += 1
        label = relative_label(skill_file, root_dir)
        if write:
            skill_file.write_text(updated, encoding="utf-8")
            print(f"[saved] {label}")
        else:
            print(f"[would save] {label}")

    actions = []
    if add_paragraph:
        actions.append("added paragraph")
    if remove_paragraph:
        actions.append("removed paragraph")
    if patch_missing_tags:
        actions.append("patched missing tags")
    summary_word = ", ".join(actions) if actions else "updated"
    if write:
        print(f"[*] Updated {changed_count} SKILL.md file(s): {summary_word}.")
    else:
        print(f"[*] Dry run complete. {changed_count} SKILL.md file(s) would be updated: {summary_word}.")

    return changed_count


def main():
    parser = argparse.ArgumentParser(
        description="Add or remove the telemetry notice in user SKILL.md files."
    )
    parser.add_argument(
        "--target",
        type=str,
        default=str(default_target()),
        help="Root folder to search. Defaults to ~/.agents/skills.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write changes to disk. Without this flag, the script runs as a dry run.",
    )
    parser.add_argument(
        "--add-paragraph",
        action="store_true",
        help="Add the telemetry paragraph to each SKILL.md.",
    )
    parser.add_argument(
        "--remove-paragraph",
        action="store_true",
        help="Remove the telemetry paragraph from each SKILL.md.",
    )
    parser.add_argument(
        "--patch-missing-tags",
        action="store_true",
        help="Also add missing dispatcher-* tags in frontmatter using the enrichment manifest.",
    )
    parser.add_argument(
        "--enrichments",
        type=str,
        default=str(default_enrichments_path()),
        help="Path to the enrichment manifest used for --patch-missing-tags.",
    )
    args = parser.parse_args()

    root_dir = Path(args.target).expanduser().resolve()
    if not root_dir.exists():
        raise SystemExit(f"[!] Target directory does not exist: {root_dir}")

    if not any([args.add_paragraph, args.remove_paragraph, args.patch_missing_tags]):
        raise SystemExit("[!] Select at least one action: --add-paragraph, --remove-paragraph, or --patch-missing-tags")

    if args.add_paragraph and args.remove_paragraph:
        raise SystemExit("[!] Use either --add-paragraph or --remove-paragraph, not both.")

    enrichments = {}
    if args.patch_missing_tags:
        enrichments_path = Path(args.enrichments).expanduser().resolve()
        if not enrichments_path.exists():
            raise SystemExit(f"[!] Enrichment manifest does not exist: {enrichments_path}")
        enrichments = load_enrichments(enrichments_path)

    process_files(
        root_dir,
        args.add_paragraph,
        args.remove_paragraph,
        args.write,
        args.patch_missing_tags,
        enrichments,
    )


if __name__ == "__main__":
    main()
