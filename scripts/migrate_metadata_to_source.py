import json
import os
import re
import argparse
from pathlib import Path

def migrate_metadata(skills_root, enrichments_path, dry_run=True):
    skills_root = Path(skills_root)
    enrichments_all = {}
    
    if os.path.exists(enrichments_path):
        with open(enrichments_path, "r", encoding="utf-8") as f:
            enrichments_all = json.load(f)
    
    print(f"[*] Starting migration scan in {skills_root}...")
    if dry_run:
        print("[!] DRY RUN MODE: No files will be modified.")

    modified_count = 0
    skipped_count = 0
    error_count = 0

    # Iterate over directories in skills_root
    for skill_dir in skills_root.iterdir():
        if not skill_dir.is_dir():
            continue
            
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue

        try:
            content = skill_file.read_text(encoding="utf-8")
            
            # Extract frontmatter
            match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
            if not match:
                continue
                
            frontmatter = match.group(1)
            
            # Check if it's a dispatcher-ready skill
            if "dispatcher-" not in frontmatter:
                continue

            # Check if layer already exists
            if "dispatcher-layer:" in frontmatter:
                print(f"[-] {skill_dir.name}: Existing layer found. Skipping.")
                skipped_count += 1
                continue

            # Determine Target Layer
            # We use the folder name as the skill key lookup
            skill_name = skill_dir.name.lower()
            enrichment = enrichments_all.get(skill_name, {})
            target_layer = enrichment.get("layer", "execution") # Default to execution
            
            # Prepare injection lines
            injection = f"    dispatcher-layer: {target_layer}\n    dispatcher-lifecycle: active\n"
            
            # Locate the metadata: block
            # This regex looks for 'metadata:' and injects the new lines after it
            new_frontmatter = re.sub(
                r"(metadata:\s*\n)", 
                rf"\1{injection}", 
                frontmatter, 
                count=1
            )
            
            # If for some reason metadata: block isn't found but dispatcher- tags are present
            # we might need to append them to the end of the frontmatter? 
            # But based on our standard, metadata: should be there.
            if new_frontmatter == frontmatter:
                # Fallback: check if metadata is just missing as a header but tags are present
                # This is unlikely in our standard but let's be safe.
                if "metadata:" not in frontmatter:
                    # Append to end of frontmatter
                    new_frontmatter = frontmatter.rstrip() + f"\nmetadata:\n{injection}"
            
            if new_frontmatter != frontmatter:
                new_content = content.replace(frontmatter, new_frontmatter)
                
                if not dry_run:
                    skill_file.write_text(new_content, encoding="utf-8")
                    print(f"[+] {skill_dir.name}: Metadata injected ({target_layer})")
                else:
                    print(f"[*] {skill_dir.name}: Would inject ({target_layer})")
                
                modified_count += 1
            else:
                print(f"[?] {skill_dir.name}: Could not locate insertion point.")
                error_count += 1

        except Exception as e:
            print(f"[!] {skill_dir.name}: Error processing file: {e}")
            error_count += 1

    print("\n" + "="*40)
    print(f"Migration Summary ({'Dry Run' if dry_run else 'Live'})")
    print(f"  Modified: {modified_count}")
    print(f"  Skipped:  {skipped_count}")
    print(f"  Errors:   {error_count}")
    print("="*40)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate dispatcher metadata to skill source files.")
    parser.add_argument("--root", default="C:/projects/skills", help="Root directory of core skills")
    parser.add_argument("--enrichments", default="../config/skill_enrichments.json", help="Path to enrichments JSON")
    parser.add_argument("--no-dry-run", action="store_true", help="Execute the migration (omit for dry run)")
    
    args = parser.parse_args()
    
    # Resolve enrichment path relative to script
    script_dir = Path(__file__).parent
    enrichments_abs = (script_dir / args.enrichments).resolve()
    
    migrate_metadata(args.root, str(enrichments_abs), dry_run=not args.no_dry_run)
