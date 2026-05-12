#!/usr/bin/env python3
"""Enforce Telemetry - Audits and patches Skill files to ensure dispatcher logging compliance.
Now with de-duplication and pattern normalization.

DEPRECATED: Use skill_md_telemetry_notice.py instead.
  skill_md_telemetry_notice.py is a strict superset of this script:
  - Same telemetry paragraph add/remove behaviour
  - Also patches missing dispatcher-* frontmatter tags (--patch-missing-tags)
  - Supports --target for non-default skill roots

Migration:
  enforce_telemetry.py --patch          ->  skill_md_telemetry_notice.py --add-paragraph --write
  enforce_telemetry.py --patch --target ->  skill_md_telemetry_notice.py --add-paragraph --target <path> --write

This file is kept for backwards compatibility and will be removed in a future release.
"""
import warnings
warnings.warn(
    "enforce_telemetry.py is deprecated. Use skill_md_telemetry_notice.py instead.",
    DeprecationWarning,
    stacklevel=1,
)

import os
import argparse
import re
from pathlib import Path

# The canonical snippet to use
LOGGING_SNIPPET = """
## Telemetry & Logging
> [!IMPORTANT]
> All usage of this skill must be logged via the Skill Dispatcher to ensure audit logs and wallboard analytics are accurate:
> `./log-dispatch.cmd --skill <skill_name> --intent <intent> --model <model_name> --reason <reason>` (or `./log-dispatch.sh` on Linux)
"""

# Regex to find existing telemetry sections (to remove/replace them).
#
# Safety note: stop before any next Markdown ATX heading, including a top-level
# "# Title". Earlier versions stopped only before "##", which could delete the
# skill's real body title when telemetry appeared before it.
TELEMETRY_SECTION_PATTERN = re.compile(
    r"^[ \t]{0,3}##[ \t]+Telemetry & Logging[ \t]*\n.*?(?=^[ \t]{0,3}#{1,6}[ \t]+|\Z)",
    re.DOTALL | re.MULTILINE,
)
FRONTMATTER_PATTERN = re.compile(r"^(\ufeff?---[ \t]*\r?\n.*?\r?\n---[ \t]*\r?\n)", re.DOTALL)

def split_frontmatter(content: str):
    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        return None, content
    return match.group(1).rstrip(), content[match.end():]

def audit_skills(root_dir, patch=False):
    root_dir = Path(root_dir).resolve()
    print(f"[*] Auditing skills in: {root_dir}")
    skill_files = list(root_dir.rglob("SKILL.md"))
    print(f"[*] Found {len(skill_files)} SKILL.md files.")
    
    modified_count = 0
    for skill_file in skill_files:
        try:
            content = skill_file.read_text(encoding="utf-8")
            
            # Check for both old and new patterns
            has_old = "dispatch_logger.py" in content
            has_new = "log-dispatch.cmd" in content
            has_section = "## Telemetry & Logging" in content
            
            # If we have multiple sections or a mix of old/new, we should patch (normalize)
            existing_sections = TELEMETRY_SECTION_PATTERN.findall(content)
            is_redundant = len(existing_sections) > 1
            is_outdated = has_old and not has_new
            
            if not has_section or is_redundant or is_outdated:
                print(f" [!] Needs telemetry update: {skill_file.relative_to(root_dir)}")
                
                if patch:
                    # 1. Strip all existing telemetry sections
                    new_content = TELEMETRY_SECTION_PATTERN.sub("", content)
                    
                    # 2. Insert the fresh snippet
                    # Try to insert after frontmatter or before first heading
                    frontmatter, body = split_frontmatter(new_content)
                    if frontmatter is not None:
                        # Insert at the top of the body after real YAML frontmatter.
                        new_content = f"{frontmatter}\n\n{LOGGING_SNIPPET.strip()}\n\n{body.strip()}"
                    else:
                        # Fallback: append
                        new_content = new_content.strip() + "\n\n" + LOGGING_SNIPPET.strip()
                    
                    # Final cleanup of excessive newlines
                    new_content = re.sub(r"\n{3,}", "\n\n", new_content)
                    
                    skill_file.write_text(new_content, encoding="utf-8")
                    modified_count += 1
        except Exception as e:
            print(f" [!] Error processing {skill_file}: {e}")
            
    if patch:
        print(f"[*] Patched {modified_count} skill files with normalized telemetry hooks.")
    else:
        print(f"[*] Audit complete. {modified_count} files would be updated. Run with --patch to apply.")

def main():
    parser = argparse.ArgumentParser(description="Enforce Telemetry on Skills")
    parser.add_argument("--patch", action="store_true", help="Apply telemetry hooks to missing skills")
    parser.add_argument("--target", type=str, help="Target directory to audit (default: parent of script)")
    args = parser.parse_args()
    
    # Correctly identify the skills root
    script_file_path = Path(__file__).resolve()
    # If script is in skill-dispatcher/scripts/enforce_telemetry.py
    # script_dir is skill-dispatcher
    # parent is the directory containing skill-dispatcher (likely where all skills live)
    script_dir = script_file_path.parent.parent
    
    if args.target:
        skills_root = Path(args.target)
    else:
        skills_root = script_dir.parent
    
    audit_skills(skills_root, patch=args.patch)

if __name__ == "__main__":
    main()
