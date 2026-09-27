# Skill-usage telemetry hooks

These hooks replace the "CRITICAL TELEMETRY REQUIREMENT" notice that asked the *model* to run `log-dispatch`. Each harness now calls one script, `skill_usage_hook.py`, on its own lifecycle events. The script writes the same event format through `scripts/dispatch_logger.py`, so `dispatch_events.jsonl`, the Honcho sync and `reports/wallboard.html` keep working unchanged. Logging no longer depends on the model remembering to do it.

- **Installed copy:** `~/.agents/dispatcher-data/hooks/skill_usage_hook.py`. This location survives skill reinstalls. Every harness config points here.
- **Source and tests:** this folder. Run the tests with `py -3 -m unittest tests.test_skill_usage_hook`. They use synthetic payloads in each harness's real format, and nothing reaches the real log.
- **Event on the wallboard:** `intent = "skill used (via <harness> hook)"`, `reason = "hook:<harness> <event>: <how>"`, plus the model and a chain id derived from the session.

## When a skill counts as used

1. The harness's own skill tool ran: `Skill` in Claude Code, `activate_skill` in Gemini CLI.
2. A tool read `<runtime skills root>/<skill>/…/SKILL.md`. Codex, Grok and Antigravity load skills this way, and Claude sometimes does too. A nested sub-skill counts toward its parent (`playwright-skill/core/SKILL.md` → playwright-skill).
3. The user invoked the skill explicitly: `/skill` in Claude Code, Grok or Gemini, or `$skill` in Codex.

Only installed skills under `~/.agents`, `~/.claude`, `~/.codex`, `~/.gemini` (including `antigravity/`), `~/.grok` or `~/.cursor` count. Reading a SKILL.md in `C:\projects\skills` is authoring, not usage. Each skill is logged once per session per 30 minutes.

The hook never blocks the harness. Errors go to `~/.agents/dispatcher-data/hooks/errors.log`, and the script always exits 0. To dump raw payloads while debugging, create `~/.agents/dispatcher-data/hooks/debug.flag`; payloads then land in `debug-payloads/`. Remove the flag afterwards, because prompts are stored too.

## Per harness

The command in every registration is `py -3 C:/Users/jochi/.agents/dispatcher-data/hooks/skill_usage_hook.py --harness <name>`.

### Claude Code

**Config:** `~/.claude/settings.json` → `hooks`

| Event | Matcher | What it catches |
|---|---|---|
| `PostToolUse` | `Skill\|Read` | `tool_input.skill`, or a Read of a runtime SKILL.md |
| `UserPromptSubmit` | – | `/skill` typed by the user. This expands without any tool call. |
| `Stop` | – | Logs the pending `/skill` once the model is known |

All three registrations run with `async: true` and a 30 s timeout.

The model name is not in Claude's payload. It is read from `transcript_path`, the last assistant `message.model`.

Grok also executes `~/.claude/settings.json` hooks. The script sees `GROK_HOOK_EVENT` and exits, so Grok's own registration is the only one that logs.

### OpenAI Codex CLI

**Config:** `~/.codex/hooks.json`

| Event | Matcher | What it catches |
|---|---|---|
| `PostToolUse` | `*` (all tools) | A SKILL.md read such as `Get-Content -Raw '…\SKILL.md'`. Codex's code mode runs shell commands through a tool named `exec`, not `Bash`, so the matcher covers every tool and the script filters. |
| `UserPromptSubmit` | – | `$skill` mentions |
| `Stop` | – | |

`command` and `commandWindows` are identical (`python …`: the `py` launcher is not on the PATH Codex gives its shell), and the registrations use `async: true`. The model comes from the payload's `model` field.

Approval is tied to the file's hash: any edit to `hooks.json` needs a fresh approval in `/hooks`. The desktop app (codex-cli 0.155) and an older terminal `codex` may not share the same approval state.

**One-time step:** Codex runs a new hook only after you approve it. Start `codex`, run `/hooks`, and trust "skill telemetry". Do not use `--dangerously-bypass-hook-trust`.

### Gemini CLI

**Config:** `~/.gemini/settings.json` → `hooks`

| Event | Matcher | What it catches |
|---|---|---|
| `AfterTool` | `activate_skill\|read_file\|read_many_files\|run_shell_command` | `activate_skill` `{name}`, or a SKILL.md read |
| `BeforeAgent` | – | Prompts |
| `AfterAgent` | – | Turn end |

Timeouts are in milliseconds. The script prints `{}` because Gemini requires JSON on stdout. The model comes from the transcript.

**Limitation (September 2026):** Google rejects Gemini CLI for personal OAuth accounts ("migrate to the Antigravity suite"). It only works with `GEMINI_API_KEY`.

### Google Antigravity (IDE and Antigravity 2.0)

**Config:** `~/.gemini/config/hooks.json`, as a named hook `skill-telemetry`

| Event | Matcher | What it catches |
|---|---|---|
| `PostToolUse` | `view_file\|run_command` | A SKILL.md read |
| `Stop` | – | Also scans the transcript for SKILL.md reads written since the last scan (a safety net; the live test on 2026-09-27 showed `PostToolUse` does carry `toolCall`) |

Antigravity's payload has no event name, so the registration passes `--event`. It uses camelCase fields: `toolCall.name`, `toolCall.args`, `conversationId`, `modelName`.

Two format rules from Antigravity's built-in `agy-customizations/docs/hooks.md`:
- `Stop`, `PreInvocation` and `PostInvocation` take a **flat** list of handlers. Only the tool events use the `{matcher, hooks}` wrapper.
- Every hook must print a JSON object on stdout; the script prints `{}`.

The transcript stores tool arguments as JSON-in-JSON, so paths carry doubled backslashes.

The Antigravity CLI (`agy`) reads `~/.gemini/antigravity-cli/settings.json` instead. It is not installed on this machine.

### xAI Grok CLI

**Config:** `~/.grok/hooks/skill-telemetry.json`. Global hooks there are always trusted.

| Event | Matcher | What it catches |
|---|---|---|
| `PostToolUse` | all tools | Grok lists each skill's absolute SKILL.md path and reads it with `read_file` |
| `UserPromptSubmit` | – | `/skill` and `/user:skill` |
| `Stop` | – | |

The timeout is set to 30 s, because Grok's default is 5 s. Grok's payload is camelCase (`toolName`, `toolInput`, `sessionId`). It carries no model name; the script reads `modelId` from the session transcript (`updates.jsonl`). `grok inspect --json` lists the loaded hooks.

## Proof

Live-proven on 2026-09-27: Claude Code, Codex, Grok and Antigravity (`C:\projects\VS_prj\SkillRework\proof60927-134546-wallboard-all-harnesses.png`). Gemini CLI is unit-tested only, because Google no longer accepts personal OAuth for it.

`C:\projects\VS_prj\SkillRework\tools\live_hook_tests.py` runs each CLI headless against the `booklet-droodle` skill. Shell access is off where the CLI allows it, so only the hook can produce the event. It then calls `wallboard_proof.py`, which regenerates the wallboard, opens `file:///C:/Users/jochi/.agents/dispatcher-data/reports/wallboard.html`, and screenshots the Recent Activity rows the hooks produced.
