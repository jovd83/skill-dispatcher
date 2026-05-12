#!/usr/bin/env python3
"""Harden Telemetry Workflow - Injects Step 0 into Skill workflows.
Enforces the 'Clean Compromise':
1. Standard header paragraph.
2. Step 0 in the workflow section.
"""

import argparse
import re
from pathlib import Path

# The canonical header snippet
HEADER_NOTICE = """## Telemetry & Logging

> [!IMPORTANT]
> **CRITICAL TELEMETRY REQUIREMENT**: Every execution of this skill MUST be logged immediately. Omitting this step violates the system's audit integrity policy.
> Run: `%USERPROFILE%\\.agents\\skills\\skill-dispatcher\\log-dispatch.cmd --skill {skill_name} --intent <intent> --model <model_name> --reason <reason>`
"""

# The canonical Workflow Step 0
STEP_0_BLOCK = """0. **Telemetry Logging (MANDATORY):**
   - **Action:** Run the `log-dispatch.cmd` command mentioned in the Telemetry section above as your **VERY FIRST** tool call.
   - **Reason:** Ensures the wallboard reflects active work and prevents "Staleness" alerts.
"""

# Regex to find the Telemetry header section.
#
# Safety note: stop before any next Markdown ATX heading, including a top-level
# "# Title". Earlier versions stopped only before "##", which could delete the
# skill's real body title when telemetry appeared before it.
HEADER_PATTERN = re.compile(
    r"^[ \t]{0,3}##[ \t]+Telemetry & Logging[ \t]*\n.*?(?=^[ \t]{0,3}#{1,6}[ \t]+|\Z)",
    re.DOTALL | re.MULTILINE,
)

# Regex to find Workflow headers (matches "## Workflow", "## Core Workflow", etc. with flexible spacing)
WORKFLOW_PATTERN = re.compile(r"(## (?:[\w-]+\s+)*Workflow[ \t]*\n+)", re.IGNORECASE)
FRONTMATTER_PATTERN = re.compile(r"^(\ufeff?---[ \t]*\r?\n.*?\r?\n---[ \t]*\r?\n)", re.DOTALL)

def default_target() -> Path:
    return Path.home() / ".agents" / "skills"

def split_frontmatter(content: str):
    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        return None, content
    return match.group(1).rstrip(), content[match.end():]

def process_skill(file_path: Path, write: bool):
    skill_name = file_path.parent.name
    content = file_path.read_text(encoding="utf-8")
    original_content = content
    
    # 1. Handle the Header
    header_text = HEADER_NOTICE.format(skill_name=skill_name).strip()
    if "## Telemetry & Logging" in content:
        # Update existing header
        # Escape backslashes in header_text for re.sub
        safe_header_text = header_text.replace("\\", "\\\\")
        content = HEADER_PATTERN.sub(safe_header_text + "\n\n", content)
    else:
        # Inject after frontmatter
        frontmatter, body = split_frontmatter(content)
        if frontmatter is not None:
            content = f"{frontmatter}\n\n{header_text}\n\n{body.strip()}"
        else:
            content = f"{header_text}\n\n{content.strip()}"

    # 2. Handle Step 0 in Workflow
    if "0. **Telemetry Logging" not in content:
        workflow_match = WORKFLOW_PATTERN.search(content)
        if workflow_match:
            # Inject Step 0 after the header
            insert_pos = workflow_match.end()
            content = content[:insert_pos] + STEP_0_BLOCK + "\n" + content[insert_pos:]
        else:
            # If no workflow section found, we don't force Step 0 yet
            # (Some skills might use different heading structures)
            pass

    # Final cleanup of excessive newlines
    content = re.sub(r"\n{3,}", "\n\n", content).strip() + "\n"

    if content != original_content:
        if write:
            file_path.write_text(content, encoding="utf-8")
            print(f"[updated] {file_path.name} in {skill_name}")
        else:
            print(f"[would update] {file_path.name} in {skill_name}")
        return True
    return False

def main():
    parser = argparse.ArgumentParser(description="Harden Telemetry Workflow in SKILL.md files")
    parser.add_argument("--target", type=str, default=str(default_target()), help="Directory to scan")
    parser.add_argument("--write", action="store_true", help="Apply changes to disk")
    args = parser.parse_args()

    root_dir = Path(args.target).expanduser().resolve()
    if not root_dir.exists():
        print(f"[!] Directory not found: {root_dir}")
        return

    print(f"[*] Scanning for skills in: {root_dir}")
    skill_files = list(root_dir.rglob("SKILL.md"))
    print(f"[*] Found {len(skill_files)} SKILL.md files.")

    changed = 0
    for f in skill_files:
        if process_skill(f, args.write):
            changed += 1

    if args.write:
        print(f"[*] Finished. Updated {changed} skills.")
    else:
        print(f"[*] Dry run complete. {changed} skills would be updated.")

if __name__ == "__main__":
    main()
