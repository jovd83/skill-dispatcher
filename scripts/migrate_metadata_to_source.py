#!/usr/bin/env python3
"""Migrate Metadata - Enforces STRICT Dispatcher Schema.
Ensures all standard tags are present in every SKILL.md.
"""

import json
import os
import re
import argparse
from pathlib import Path

# The standard set of tags we want in EVERY skill
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
    "dispatcher-persistent-directories"
]

def migrate_metadata(skills_root, enrichments_path, dry_run=True):
    skills_root = Path(skills_root).resolve()
    enrichments_all = {}
    
    if os.path.exists(enrichments_path):
        with open(enrichments_path, "r", encoding="utf-8") as f:
            enrichments_all = json.load(f)
    
    print(f"[*] Starting strict schema enforcement in {skills_root}...")
    
    skill_files = list(skills_root.rglob("SKILL.md"))
    print(f"[*] Found {len(skill_files)} SKILL.md files.")

    if dry_run:
        print("[!] DRY RUN MODE: No files will be modified.")

    modified_count = 0
    skipped_count = 0
    error_count = 0

    for skill_file in skill_files:
        skill_dir = skill_file.parent
        skill_name = skill_dir.name.lower()
        enrichment = enrichments_all.get(skill_name, {})
        
        try:
            content = skill_file.read_text(encoding="utf-8")
            match = re.search(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
            if not match:
                continue
                
            frontmatter = match.group(1)
            
            # Check for strict compliance (do all standard keys exist?)
            is_compliant = all(f"{key}:" in frontmatter for key in STANDARD_SCHEMA)
            if is_compliant:
                skipped_count += 1
                continue

            # Build injection block
            lines = []
            
            # 1. Identity
            layer = enrichment.get("layer", "execution")
            category = enrichment.get("category", layer)
            lines.append(f"  dispatcher-category: {category}")
            lines.append(f"  dispatcher-layer: {layer}")
            lines.append(f"  dispatcher-lifecycle: active")
            
            # 2. Safety
            risk = enrichment.get("risk", "low")
            writes_files = str(enrichment.get("writes_files", "false")).lower()
            lines.append(f"  dispatcher-risk: {risk}")
            lines.append(f"  dispatcher-writes-files: {writes_files}")

            # 3. Capabilities and Contracts (Enforce all even if empty)
            mappings = {
                "capabilities": "dispatcher-capabilities",
                "accepted_intents": "dispatcher-accepted-intents",
                "input_artifacts": "dispatcher-input-artifacts",
                "output_artifacts": "dispatcher-output-artifacts",
                "stack_tags": "dispatcher-stack-tags",
                "persistent_directories": "dispatcher-persistent-directories"
            }
            
            for json_key, yaml_key in mappings.items():
                val = enrichment.get(json_key, [])
                if isinstance(val, list):
                    csv_val = ", ".join(val)
                    lines.append(f"  {yaml_key}: {csv_val}")
                else:
                    lines.append(f"  {yaml_key}: {val}")
            
            # 4. Tags
            tags = enrichment.get("tags", [])
            if tags:
                lines.append("  metadata-tags:")
                for tag in tags:
                    lines.append(f"    - {tag}")
            
            injection = "\n".join(lines) + "\n"
            
            # REPLACE partial metadata to avoid duplicates then inject fresh block
            new_frontmatter = frontmatter
            if "metadata:" in frontmatter:
                # Remove ANY existing dispatcher- tags inside the metadata block
                new_frontmatter = re.sub(r"  dispatcher-.*?\n(?! )", "", frontmatter, flags=re.DOTALL)
                new_frontmatter = re.sub(r"  metadata-tags:.*?\n(?! )", "", new_frontmatter, flags=re.DOTALL)
                # Inject the fresh standard block
                new_frontmatter = re.sub(r"(metadata:\s*\n)", rf"\1{injection}", new_frontmatter, count=1)
            else:
                new_frontmatter = frontmatter.rstrip() + f"\nmetadata:\n{injection}"
            
            if new_frontmatter != frontmatter:
                new_content = content.replace(frontmatter, new_frontmatter)
                
                if not dry_run:
                    skill_file.write_text(new_content, encoding="utf-8")
                    print(f"[+] {skill_name}: Strict schema enforced")
                else:
                    print(f"[*] {skill_name}: Would enforce strict schema")
                
                modified_count += 1
            else:
                error_count += 1

        except Exception as e:
            print(f"[!] {skill_name}: Error: {e}")
            error_count += 1

    print("\n" + "="*40)
    print(f"Strict Schema Migration Summary ({'Dry Run' if dry_run else 'Live'})")
    print(f"  Modified: {modified_count}")
    print(f"  Skipped:  {skipped_count}")
    print(f"  Errors:   {error_count}")
    print("="*40)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Strict schema enforcement.")
    parser.add_argument("--root", help="Skills root")
    parser.add_argument("--no-dry-run", action="store_true")
    args = parser.parse_args()
    
    script_path = Path(__file__).resolve()
    script_dir = script_path.parent.parent
    skills_root = Path(args.root) if args.root else script_dir.parent
    enrichments = (script_dir / "config" / "skill_enrichments.json").resolve()
    
    migrate_metadata(skills_root, str(enrichments), dry_run=not args.no_dry_run)
