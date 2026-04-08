import os
import sys
import datetime
from pathlib import Path

def parse_frontmatter(content):
    """
    Improved YAML frontmatter parser for AgentSkills.
    Handles multi-line values, lists, and booleans without external dependencies.
    """
    if not content.startswith('---'):
        return {}
    
    lines = content.splitlines()
    end_index = -1
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == '---':
            end_index = i
            break
            
    if end_index == -1:
        return {}

    metadata = {}
    current_key = None
    is_multiline = False
    
    for line in lines[1:end_index]:
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
            
        if ':' in line and not (line.startswith(' ') or line.startswith('\t')):
            key, val = line.split(':', 1)
            current_key = key.strip()
            val = val.strip()
            is_multiline = False
            
            # YAML multi-line markers
            if val in ('|', '|-', '>', '>-'):
                metadata[current_key] = ""
                is_multiline = True
            else:
                # Boolean parsing
                if val.lower() in ('true', 'yes', 'on'):
                    metadata[current_key] = True
                elif val.lower() in ('false', 'no', 'off'):
                    metadata[current_key] = False
                # List parsing: [a, b]
                elif val.startswith('[') and val.endswith(']'):
                    metadata[current_key] = [v.strip().strip("'").strip('"') for v in val[1:-1].split(',')]
                else:
                    metadata[current_key] = val.strip("'").strip('"')
        elif current_key and (line.startswith(' ') or line.startswith('\t')):
            # Continuation of value
            if is_multiline:
                metadata[current_key] += (line[2:] if line.startswith('  ') else line.strip()) + "\n"
            else:
                if isinstance(metadata[current_key], str):
                    metadata[current_key] += " " + stripped
                    
    return {k: (v.strip() if isinstance(v, str) else v) for k, v in metadata.items()}

def normalize_field(key, val):
    """Normalize common metadata fields for enterprise-grade consistency."""
    if not isinstance(val, str):
        return val
    
    clean_val = val.lower().strip()
    if key == 'risk':
        if any(w in clean_val for w in ('high', 'critical', 'extreme', '3')): return 'high'
        if any(w in clean_val for w in ('low', 'minimal', '1')): return 'low'
        return 'medium'
    
    if key == 'category':
        if any(w in clean_val for w in ('test', 'qa', 'automation', 'coverage')): return 'testing'
        if any(w in clean_val for w in ('sec', 'audit', 'vuln', 'protection')): return 'security'
        if any(w in clean_val for w in ('analyze', 'req', 'feat', 'planning')): return 'analysis'
        if any(w in clean_val for w in ('dev', 'ops', 'deploy', 'infra')): return 'infrastructure'
        
    return val

def find_skills(scan_dirs):
    """Discovers and validates skills in the provided directories."""
    skills = {}
    print(f"[*] Scanning for skills in: {', '.join(str(d) for d in scan_dirs)}")
    
    for d in scan_dirs:
        p = Path(d)
        if not p.exists() or not p.is_dir():
            continue
        
        try:
            for folder in p.iterdir():
                if not folder.is_dir() or folder.name.startswith('.'):
                    continue
                
                skill_file = folder / "SKILL.md"
                if not skill_file.exists():
                    continue
                
                try:
                    content = skill_file.read_text(encoding='utf-8')
                    fm = parse_frontmatter(content)
                    name = fm.get('name') or folder.name
                    
                    if name == 'skill-dispatcher':
                        continue
                    
                    if not fm.get('description'):
                        print(f" [!] Warning: Skill '{name}' in {folder.name} is missing a description.")
                    
                    if name in skills:
                        print(f" [!] Skipping duplicate skill: {name} (found in {skills[name]['source']})")
                        continue
                    
                    # Normalization
                    fm['risk'] = normalize_field('risk', fm.get('risk', 'medium'))
                    fm['category'] = normalize_field('category', fm.get('category', 'uncategorized'))
                    
                    skills[name] = {
                        'metadata': fm,
                        'path': str(folder.absolute()),
                        'source': str(p.absolute())
                    }
                except Exception as e:
                    print(f" [!] Error parsing skill in {folder}: {e}")
        except Exception as e:
            print(f" [!] Error accessing directory {p}: {e}")
                
    return skills

def main():
    print("=== AgentSkill Registry Builder ===")
    
    # 1. Determine paths
    current_script = Path(__file__).resolve()
    skill_root = current_script.parent.parent
    
    scan_dirs = set()
    # A. Parent directory (Common skill install location)
    if skill_root.parent and skill_root.parent != skill_root:
        scan_dirs.add(skill_root.parent)
    
    # B. Development mode (Inside a 'skills/' folder)
    repo_root = skill_root.parent.parent
    local_skills_dir = repo_root / "skills"
    if local_skills_dir.exists() and local_skills_dir.is_dir():
        scan_dirs.add(local_skills_dir)
        
    # C. Sibling skills directory
    if repo_root.parent and repo_root.parent.name == "skills":
        scan_dirs.add(repo_root.parent)
        
    # D. Global Agent skills directory
    global_agent_skills = Path.home() / ".agents" / "skills"
    if global_agent_skills.exists() and global_agent_skills.is_dir():
        scan_dirs.add(global_agent_skills)
        
    # E. External overrides
    extra_dirs = os.environ.get('SKILL_DISPATCHER_EXTRA_DIRS', '')
    if extra_dirs:
        for d in extra_dirs.split(os.pathsep):
            if d.strip():
                scan_dirs.add(Path(d.strip()))
                
    # 2. Run discovery
    skills = find_skills(scan_dirs)
    registry_path = skill_root / "registry" / "SKILL_REGISTRY.md"
    
    if not skills:
        print("[*] No additional skills discovered.")
        msg = f"# Skill Registry\n\n*Last updated: {datetime.datetime.now().isoformat()}*\n\nNo skills discovered yet."
        registry_path.write_text(msg, encoding='utf-8')
        return

    # 3. Organize by category
    by_category = {}
    for name, data in skills.items():
        cat = data['metadata'].get('category', 'uncategorized')
        by_category.setdefault(cat, []).append((name, data))
        
    # 4. Generate Registry Document
    lines = [
        "# Skill Registry",
        "",
        f"This registry was automatically generated on **{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**.",
        f"Total active skills: **{len(skills)}**",
        "",
        "---",
        ""
    ]
    
    for cat in sorted(by_category.keys()):
        lines.append(f"## Category: {cat.upper()}")
        for name, data in sorted(by_category[cat]):
            fm = data['metadata']
            lines.append(f"### `{name}`")
            lines.append(f"- **Description**: {fm.get('description', '*No description provided.*')}")
            
            tags = fm.get('tags')
            if tags:
                tag_str = ", ".join(tags) if isinstance(tags, list) else str(tags)
                lines.append(f"- **Tags**: `{tag_str}`")
            
            lines.append(f"- **Risk**: `{fm.get('risk', 'medium')}`")
            lines.append(f"- **Location**: `{data['path']}`")
            lines.append("")
            
    try:
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text("\n".join(lines), encoding='utf-8')
        print(f"[*] Successfully built registry at: {registry_path}")
    except Exception as e:
        print(f"[!] Critical Error: Failed to write registry: {e}")
        sys.exit(1)
        
    # 5. Final summary
    print("\n--- Discovery Summary ---")
    for name, data in sorted(skills.items()):
        cat = data['metadata'].get('category', 'UNCATEGORIZED')
        print(f"[{cat:^14}] {name}")
    print("--------------------------\n")

if __name__ == "__main__":
    main()
