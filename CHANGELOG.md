# Changelog

## 4.0.1 — 2026-09-27

### Changed
- `build_registry.py --preflight` looks for `normalize()` in `skill-lint`, the new name of `skill-yaml-cleanup`, before the old folder names.
- `.skill-lint.json` skips skill-lint's telemetry check for this repository: the dispatcher documents the logger that the hooks call, which is not a model-run telemetry instruction.

## 4.0.0 — 2026-09-27

The dispatcher becomes an analytics skill. Usage is logged by harness hooks instead of by the model.

### Added
- `hooks/skill_usage_hook.py`: one hook for Claude Code, OpenAI Codex, xAI Grok, Google Antigravity, Gemini CLI, GitHub Copilot and Hermes Agent, with per-harness documentation in `hooks/README.md` and offline tests.
- `disable-model-invocation: true`: Claude Code no longer loads the skill on its own.

### Changed
- `SKILL.md` rewritten around the analytics tasks: wallboard, registry, staleness audit, and skill recommendation on request.
- README rewritten to the house standard.
- The Honcho mirror is opt-in. `scripts/sync_to_honcho.py` was added only to the installed copy (May 2026) and is now part of the repo. The logger calls it only when `SKILL_DISPATCH_HONCHO_SYNC=1`. It used to post every event and schedule a Honcho dream after each one, which filled the user representation with dispatch noise.

### Removed
- The mandatory "log every dispatch" workflow, and routing in front of every task.
- The automatic shared-memory `RoutingPolicies` lookup in `dispatch_logger.py`. Explicit `--policy-*` flags are still recorded when passed.

### Retired (still in `scripts/`, no longer part of the workflow)
- `skill_md_telemetry_notice.py --add-paragraph`, `enforce_telemetry.py`, `harden_telemetry_workflow.py`: injected or enforced the model-run telemetry notice.
- `dispatch_bootstrap.py`, `check_shared_policy.py`, `prepare_dispatch_context.py`, `suggest_routing_promotions.py`, `project_memory.py`: policy bootstrap on top of shared memory.
- `sync_skills_to_agents.py`: superseded by a manifest-driven sync that copies whole skill folders.

## 3.1.0 and earlier

Routing engine with contract-driven dispatch (HANDOFF, SEQUENCE, NO_MATCH), registry v2, shared-memory policy bootstrap, chain proposals and the usage wallboard. See the git history for details.
