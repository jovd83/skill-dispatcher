#!/usr/bin/env python3
"""Enforce Telemetry - Audits and patches Skill files to ensure dispatcher logging compliance."""

import os
import argparse
from pathlib import Path

LOGGING_SNIPPET = """
## Telemetry & Logging
> [!IMPORTANT]
> All usage of this skill must be logged via the Skill Dispatcher to ensure audit logs and wallboard analytics are accurate:
> `./log-dispatch.cmd --skill <skill_name> --intent <intent> --reason <reason>` (or `./log-dispatch.sh` on Linux)
"""

def audit_skills(root_dir, patch=False):
    print(f"[*] Auditing skills in: {root_dir}")
    skill_files = list(Path(root_dir).rglob("SKILL.md"))
    print(f"[*] Found {len(skill_files)} SKILL.md files.")
    
    modified_count = 0
    for skill_file in skill_files:
        try:
            content = skill_file.read_text(encoding="utf-8")
            if "dispatch_logger.py" not in content:
                print(f" [!] Missing telemetry: {skill_file.relative_to(root_dir)}")
                if patch:
                    # Append logging snippet before the first heading if possible, or at the end
                    if "##" in content:
                        parts = content.split("##", 1)
                        new_content = parts[0] + LOGGING_SNIPPET + "\n##" + parts[1]
                    else:
                        new_content = content + "\n" + LOGGING_SNIPPET
                    
                    skill_file.write_text(new_content, encoding="utf-8")
                    modified_count += 1
        except Exception as e:
            print(f" [!] Error processing {skill_file}: {e}")
            
    if patch:
        print(f"[*] Patched {modified_count} skill files with telemetry hooks.")
    else:
        print(f"[*] Audit complete. Run with --patch to apply logging hooks to all skills.")

def main():
    parser = argparse.ArgumentParser(description="Enforce Telemetry on Skills")
    parser.add_argument("--patch", action="store_true", help="Apply telemetry hooks to missing skills")
    parser.add_argument("--target", type=str, help="Target directory to audit (default: parent of script)")
    args = parser.parse_args()
    
    script_dir = Path(__file__).parent.parent
    if args.target:
        skills_root = Path(args.target)
    else:
        # We audit the parent directory where all skills live
        skills_root = script_dir.parent
    
    audit_skills(skills_root, patch=args.patch)

if __name__ == "__main__":
    main()
