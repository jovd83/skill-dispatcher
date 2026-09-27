---
name: skill-dispatcher
description: "Skill-library analytics: who used which skill, when, with which model, and which skills have gone stale. Regenerates the usage wallboard, rebuilds the skill registry, runs the staleness audit, and on request suggests the best-fitting skill for a task from registry metadata. Usage is logged automatically by harness hooks; this skill never has to be invoked to log anything. Use when the user asks for skill usage statistics, the wallboard, a staleness report, a registry rebuild, or explicitly asks which skill should handle something."
disable-model-invocation: true
metadata:
  dispatcher-category: analysis
  dispatcher-capabilities: usage-analytics, wallboard, skill-registry, staleness-audit, skill-recommendation
  dispatcher-accepted-intents: show_skill_usage, regenerate_wallboard, rebuild_skill_registry, audit_skill_staleness, recommend_skill
  dispatcher-input-artifacts: dispatch_log, skill_tree
  dispatcher-output-artifacts: wallboard, skill_registry, staleness_report, skill_recommendation
  dispatcher-stack-tags: analytics, telemetry, registry, skills
  dispatcher-risk: low
  dispatcher-writes-files: true
  dispatcher-persistent-directories: logs, registry, reports
  dispatcher-layer: information
  dispatcher-lifecycle: active
---

> **Author:** jovd83 | **Version:** 4.0.0 | **License:** MIT

# Skill Dispatcher

Analytics for the skill library. Since 4.0.0 the dispatcher no longer sits in front of every task: harness hooks log each skill use on their own (see `hooks/README.md`), and this skill turns that log into answers.

Run scripts from the installed copy (`~/.agents/skills/skill-dispatcher/`). Data lives outside the skill, in `~/.agents/dispatcher-data/`, so reinstalls never touch it:

| Data | Path |
|---|---|
| Usage log (one JSON event per line) | `~/.agents/dispatcher-data/logs/dispatch_events.jsonl` |
| Wallboard | `~/.agents/dispatcher-data/reports/wallboard.html` |
| Skill registry | `~/.agents/dispatcher-data/registry/SKILL_REGISTRY.json` (+ `.md`) |
| Hook script, state, debug | `~/.agents/dispatcher-data/hooks/` |

## Tasks

### Show usage / regenerate the wallboard

```
python scripts/generate_wallboard.py
```

Reads the usage log and writes the wallboard: totals, most-used skills, models, recent activity, chains and staleness. Point the user to `file:///<home>/.agents/dispatcher-data/reports/wallboard.html`. For a quick answer without the page, read the log directly: rows written by hooks have `intent` = `skill used (via <harness> hook)`.

### Rebuild the skill registry

```
python scripts/build_registry.py
```

Indexes every installed SKILL.md (name, description, `dispatcher-*` metadata) into the registry. Its preflight also reports name drift and oversized frontmatter. Rebuild after installing, removing or renaming skills.

### Staleness audit

```
python scripts/staleness_audit.py --days 90
```

Lists installed skills with no logged use in the lookback window. Treat the result as a prompt for a decision (keep, make on-demand, archive), not as a verdict: a skill that was installed recently, or that is loaded in a harness without hooks, can look unused.

### Recommend a skill (only when asked)

When the user explicitly asks which skill should handle a task:

```
python scripts/match_candidates.py --intent <normalized_intent> [--keywords k1,k2] [--stack s1,s2] [--max-risk medium] --format text
```

Answer with the top candidate, the runner-up, and one line on why, grounded in the matched metadata fields. Do not perform the task yourself as part of the recommendation, and do not route tasks the user did not ask to have routed: harnesses already pick skills from their descriptions.

## Logging

Nothing to do. The hooks call `scripts/dispatch_logger.py` for every skill use in Claude Code, Codex, Grok and Antigravity (Copilot and Hermes are supported once registered). Do not run `log-dispatch` for normal skill use; it remains available for manual or scripted events only.

## Skill metadata schema

`build_registry.py` and `match_candidates.py` read these namespaced keys from each skill's `metadata:` block:

| Key | Meaning |
|---|---|
| `dispatcher-category`, `dispatcher-capabilities`, `dispatcher-accepted-intents` | What the skill does, as matchable terms |
| `dispatcher-input-artifacts`, `dispatcher-output-artifacts` | What it consumes and produces |
| `dispatcher-stack-tags` | Technologies it covers |
| `dispatcher-risk`, `dispatcher-writes-files` | How careful a caller must be |
| `dispatcher-layer` | `information` (reads), `execution` (changes things) or `feedback` (reviews) |
| `dispatcher-lifecycle` | `active`, `sunset` (warn) or `archived` (ignore) |

Keep list values on one line (`a, b, c`); keep everything else in the body of the SKILL.md.
