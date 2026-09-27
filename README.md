# Skill Dispatcher

[![version](https://img.shields.io/badge/version-4.0.0-blue)](CHANGELOG.md)
[![status](https://img.shields.io/badge/status-stable-3fb950)](SKILL.md)
[![category](https://img.shields.io/badge/category-analysis-0a7ea4)](SKILL.md)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=flat&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/jovd83)

`skill-dispatcher` is the usage-analytics layer for a large AgentSkill library: harness hooks log every skill use, and the skill turns that log into a wallboard, a registry and a staleness report.

## What This Skill Does

Up to 3.x the dispatcher tried to sit in front of every task. Every SKILL.md carried a notice telling the model to run `log-dispatch` first, and the dispatcher itself routed work after consulting shared memory. Models skipped the logging, every run paid for an extra tool call, and the routing duplicated what the harnesses already do from skill descriptions.

4.0.0 keeps the part that worked, the usage data, and makes collecting it deterministic. Each harness calls `hooks/skill_usage_hook.py` on its own lifecycle events. The hook recognises a skill use (the skill tool, a read of an installed SKILL.md, or an explicit `/skill`), and writes the event through `scripts/dispatch_logger.py`. It is live-proven in Claude Code, OpenAI Codex, xAI Grok and Google Antigravity, and supports GitHub Copilot and Hermes Agent.

On top of that log the skill:

- regenerates the **wallboard** (`generate_wallboard.py`): totals, most-used skills, models, recent activity, chains, staleness;
- rebuilds the **skill registry** (`build_registry.py`) from every installed SKILL.md, flagging name drift and oversized frontmatter;
- runs the **staleness audit** (`staleness_audit.py`) to find skills nobody uses any more;
- **recommends a skill** from registry metadata (`match_candidates.py`), but only when someone asks.

## What This Skill Does Not Do

- **It does not route every task.** Harnesses pick skills from their descriptions; the dispatcher only recommends when explicitly asked. The skill sets `disable-model-invocation: true`, so Claude Code never loads it on its own.
- **It does not ask models to log anything.** Logging is the hooks' job. `log-dispatch` remains for manual or scripted events only.
- **It does not read or write shared memory.** The automatic `RoutingPolicies` lookup in the logger was removed in 4.0.0, together with the shared-memory skill it depended on.
- **It does not inject anything into other skills.** `skill_md_telemetry_notice.py --add-paragraph` is retired; use `--remove-paragraph` or the rework's `strip_notices.py` to clean up old installs.
- **It is not a sync tool.** `scripts/sync_skills_to_agents.py` is superseded by a manifest-driven sync that copies whole skill folders.

## When To Use It

Use it when:

- someone asks which skills are used, how often, by which model or in which harness;
- the wallboard needs regenerating, or the registry after installing, removing or renaming skills;
- you are deciding which skills to archive or make on-demand (staleness audit);
- someone explicitly asks which skill should handle a task.

To add or debug usage logging for a harness, read `hooks/README.md`: that is configuration, not something the skill does at run time.

## Repository Layout

```
skill-dispatcher/
├── SKILL.md                       # the analytics skill (4.0.0)
├── hooks/
│   ├── skill_usage_hook.py        # one hook script for every harness
│   ├── README.md                  # per-harness registration and payload notes
│   └── tests/                     # synthetic payloads in each harness's format
├── scripts/
│   ├── dispatch_logger.py         # writes one event to dispatch_events.jsonl
│   ├── generate_wallboard.py      # usage log -> wallboard.html
│   ├── build_registry.py          # installed skills -> SKILL_REGISTRY.json/.md
│   ├── staleness_audit.py         # skills without recent use
│   ├── match_candidates.py        # metadata-scored skill recommendation
│   └── ...                        # legacy routing and shared-memory scripts, see CHANGELOG
├── config/                        # settings.json, skill relationships, enrichments
├── registry/                      # registry output when run from the repo
├── log-dispatch.cmd / .sh         # manual logging wrapper
├── generate-wallboard.cmd / .sh   # wallboard wrapper
├── build-registry.cmd / .sh       # registry wrapper
├── check-setup.cmd / .sh          # environment diagnostics
├── evals/evals.json
└── tests/                         # logger, registry, wallboard and matcher tests
```

## Installation

```bash
npx skills add jovd83/skill-dispatcher
```

Manual alternative:

```bash
git clone https://github.com/jovd83/skill-dispatcher.git
```

Then place the folder in `~/.agents/skills/skill-dispatcher/`. Python 3.8+ is required; the wallboard and registry use only the standard library.

To collect usage, install the hook once and register it in each harness you use:

1. Copy `hooks/skill_usage_hook.py` to `~/.agents/dispatcher-data/hooks/`. That location survives skill reinstalls.
2. Add the registration for each harness from `hooks/README.md`. Every registration runs `py -3 <home>/.agents/dispatcher-data/hooks/skill_usage_hook.py --harness <name>`.
3. Codex only: approve the hook once in `/hooks`.

## Usage

Run the scripts from the installed copy; data is written to `~/.agents/dispatcher-data/`.

| Task | Command |
|---|---|
| Regenerate the wallboard | `python scripts/generate_wallboard.py` |
| Rebuild the registry | `python scripts/build_registry.py` |
| Staleness audit | `python scripts/staleness_audit.py --days 90` |
| Recommend a skill | `python scripts/match_candidates.py --intent <intent> --keywords k1,k2 --format text` |
| Log an event by hand | `log-dispatch.cmd --skill <skill> --intent <intent> --model <model> --reason <reason>` |

In Claude Code the skill is invoked with `/skill-dispatcher`.

## Output Contract

Each usage event is one JSON line in `~/.agents/dispatcher-data/logs/dispatch_events.jsonl`:

```json
{"timestamp": "2026-09-27T13:44:37.733579", "selected_skill": "booklet-droodle",
 "skills_used": ["booklet-droodle"], "intent": "skill used (via antigravity hook)",
 "reason": "hook:antigravity PostToolUse: view_file read SKILL.md", "decision": "HANDOFF",
 "chain_id": "antigr-4efd4105", "model": "gemini-3.7-flash-high"}
```

Hook events always have `intent` = `skill used (via <harness> hook)`. No prompts, file contents or tool output are logged.

## Validation

```bash
py -3 -m pytest -q tests                                  # logger, registry, wallboard, matcher
cd hooks && py -3 -m unittest tests.test_skill_usage_hook # hook payloads for every harness
```

The hook tests feed each harness's real payload format through the hook with a stub logger, including invalid UTF-8, garbage input, dev-tree reads that must *not* count, and unknown skills that must be ignored.

## Contributing

Edit in this repository, then sync the folder to `~/.agents/skills/skill-dispatcher/`, and copy `hooks/skill_usage_hook.py` to `~/.agents/dispatcher-data/hooks/`. The installed copies are downstream and should never be edited directly.

## License

MIT — see [LICENSE](LICENSE).
