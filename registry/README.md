# Internal Documentation

Everything you need to know about how `skill-dispatcher` works under the hood.

## Automatic Discovery
The `skill-dispatcher` relies on `scripts/build_registry.py` to keep its information fresh. When the agent uses this skill, it runs the script to scan the current environment and generate:

- `registry/SKILL_REGISTRY.md` for human inspection
- `registry/SKILL_REGISTRY.json` as the machine-readable source of truth

## Generic Discovery Logic
The script uses `pathlib` to detect the location of `SKILL.md` (the "skill root").
1. **Repo-Development Mode**: If it detects a `skills/` directory at the repository root, it scans that first.
2. **Installed Mode**: It scans the parent directory of its own folder to find sibling skill folders.
3. **Sibling Skills Directory**: If the repo itself lives under a larger `skills/` folder, that directory is scanned next.
4. **Global Agent Skills**: It scans `~/.agents/skills` when present.
5. **Environment Overrides**: If the `SKILL_DISPATCHER_EXTRA_DIRS` environment variable is set, it scans those directories too, in the listed order.

## Deduplication and Filtering
- **Exclusion**: The script explicitly ignores `skill-dispatcher`.
- **Deduplication**: If a skill with the same `name` (from frontmatter) is found in multiple locations, the script keeps only the first one encountered in the ordered scan.
- **Robustness**: Skills without `SKILL.md` or with malformed frontmatter are skipped silently but logged to stdout.

## How to Extend
To add new routing rules, update `references/DISPATCH_POLICY.md`. To change how skills are discovered, modify `scripts/build_registry.py`.

## Metadata Parsing
The script reads the OpenSkills-required fields directly:
- `name` (Required)
- `description` (Required)
- `metadata` (Optional mapping)

Dispatcher-specific routing fields should live inside `metadata` using these namespaced keys:
- `dispatcher-category`
- `dispatcher-capabilities`
- `dispatcher-accepted-intents`
- `dispatcher-input-artifacts`
- `dispatcher-output-artifacts`
- `dispatcher-stack-tags`
- `dispatcher-downstream-skills`
- `dispatcher-risk`
- `dispatcher-writes-files`
- `dispatcher-manual-only`

Values should be stored as strings to remain spec-friendly. Comma-separated lists are supported for list-like fields.

`dispatcher-downstream-skills` is optional and is meant to document likely internal delegation performed by a specialist skill after a dispatcher `HANDOFF`. It improves visibility in the registry and UI, but it does not replace runtime telemetry.

If the skill itself should stay architecture-agnostic, store downstream relationships in `config/skill_relationships.json` instead. The registry builder merges that dispatcher-owned overlay into the generated registry without requiring changes to the upstream skill package.

For migration safety, the registry builder still tolerates top-level routing keys when they exist, but the preferred contract is metadata-based.

## Dispatch Contract

The dispatcher expects orchestrator skills to submit a normalized routing request with:

- `intent`
- `current_artifact_type`
- `target_artifact_type`
- `repo_context`
- `constraints`
- `preferred_stack`
- `allowed_write_risk`

The dispatcher returns:

- `decision`
- `selected_skill`
- `reason`
- `handoff_payload`

This keeps sibling skills from hardcoding one another by name or absolute path while staying compatible with the OpenSkills frontmatter format.
