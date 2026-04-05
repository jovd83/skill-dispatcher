# Internal Documentation

Everything you need to know about how `skill-dispatcher` works under the hood.

## Automatic Discovery
The `skill-dispatcher` relies on `scripts/build_registry.py` to keep its information fresh. When the agent uses this skill, it runs the script to scan the current environment and generate `references/SKILL_REGISTRY.md`.

## Generic Discovery Logic
The script uses `pathlib` to detect the location of `SKILL.md` (the "skill root").
1. **Installed Mode**: It scans the parent directory of its own folder (usually `~/.gemini/antigravity/skills/` or similar) to find all sibling skill folders.
2. **Repo-Development Mode**: If it detects a `skills/` directory at the repository root, it scans that as well. This allows for testing during development without installing.
3. **Environment Overrides**: If the `SKILL_DISPATCHER_EXTRA_DIRS` environment variable is set, it will scan those directories too (split by the OS path separator).

## Deduplication and Filtering
- **Exclusion**: The script explicitly ignores `skill-dispatcher`.
- **Deduplication**: If a skill with the same `name` (from frontmatter) is found in multiple locations, the script keeps only the first one it encountered.
- **Robustness**: Skills without `SKILL.md` or with malformed frontmatter are skipped silently but logged to stdout.

## How to Extend
To add new routing rules, update `references/DISPATCH_POLICY.md`. To change how skills are discovered, modify `scripts/build_registry.py`.

## Metadata Parsing
The script parses these YAML fields:
- `name` (Required)
- `description` (Required)
- `category`
- `tags`
- `risk`
- `writes_files` (boolean)
- `manual_only` (boolean)

All other fields are ignored to maintain cross-agent compatibility.
