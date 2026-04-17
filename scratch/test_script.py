from pathlib import Path

root_dir = r"C:\Users\jochi\.agents\skills"
target_file = Path(root_dir) / "codebase-context" / "SKILL.md"

if target_file.exists():
    content = target_file.read_text(encoding="utf-8")
    print(f"File exists: {target_file}")
    print(f"Contains 'dispatch_logger.py': {'dispatch_logger.py' in content}")
else:
    print(f"File NOT found: {target_file}")

skill_files = list(Path(root_dir).rglob("SKILL.md"))
print(f"Total SKILL.md found by rglob: {len(skill_files)}")
