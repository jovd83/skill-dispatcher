#!/usr/bin/env python3
"""Sync Skills - Copies SKILL.md from projects directory to agents directory.
"""

import shutil
from pathlib import Path

def sync_skills(source_root, target_root):
    source_root = Path(source_root).resolve()
    target_root = Path(target_root).resolve()
    
    print(f"[*] Syncing SKILL.md files from {source_root} to {target_root}...")
    
    # Find all SKILL.md files in the source (non-recursive to only get top-level skill folders)
    # Actually, iterate through directories in source_root
    synced = []
    skipped = []
    
    for skill_dir in source_root.iterdir():
        if skill_dir.is_dir():
            source_file = skill_dir / "SKILL.md"
            if source_file.exists():
                target_dir = target_root / skill_dir.name
                if target_dir.exists():
                    target_file = target_dir / "SKILL.md"
                    shutil.copy2(source_file, target_file)
                    synced.append(f"{skill_dir.name}/SKILL.md")
                else:
                    skipped.append(f"{skill_dir.name} (Target dir missing)")
                    
    return synced, skipped

if __name__ == "__main__":
    source = "C:/projects/skills"
    target = "C:/Users/jochi/.agents/skills"
    
    synced, skipped = sync_skills(source, target)
    
    print("\n" + "="*40)
    print(f"Sync Completion Report")
    print(f"  Successfully Copied: {len(synced)}")
    print(f"  Skipped/Missing:     {len(skipped)}")
    print("="*40)
    
    if synced:
        print("\n[+] Detailed Sync List:")
        for s in synced:
            print(f"  - {s}")
            
    if skipped:
        print("\n[!] Skipped List:")
        for s in skipped:
            print(f"  - {s}")
