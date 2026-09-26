#!/usr/bin/env python3
"""Harness hook: log AgentSkill usage to the dispatcher telemetry (dispatch_events.jsonl + wallboard).

Replaces the "CRITICAL TELEMETRY REQUIREMENT" notice that asked the *model* to run log-dispatch.
The harness calls this script on its own events, so logging no longer depends on the model.

One script serves every harness; each registration passes --harness:
  claude-code  PostToolUse(Skill|Read), UserPromptSubmit, Stop          ~/.claude/settings.json
  codex        PostToolUse(Bash), UserPromptSubmit, Stop                ~/.codex/hooks.json
  gemini       AfterTool(activate_skill|read_file|...), BeforeAgent, AfterAgent   ~/.gemini/settings.json
  antigravity  PostToolUse(view_file|run_command), Stop (with --event)  ~/.gemini/config/hooks.json
  grok         PostToolUse, UserPromptSubmit, Stop                      ~/.grok/hooks/skill-telemetry.json

A skill counts as "used" when:
  1. the harness's dedicated skill tool ran (Claude `Skill`, Gemini `activate_skill`), or
  2. any tool input references <runtime skills root>/<skill>/.../SKILL.md (Codex/Grok read it via
     shell or read_file; Claude sometimes Reads it directly), or
  3. the user prompt invokes it explicitly (`/skill` in Claude/Gemini/Grok, `$skill` in Codex).
Only installed skills under the user's runtime skill roots count; reading a SKILL.md in a
development tree is authoring, not usage. Each skill is logged once per session per 30 minutes.

The event is written by the existing skill-dispatcher/scripts/dispatch_logger.py, so the log path,
Honcho sync and wallboard regeneration are unchanged. The hook never blocks the harness: every
error is swallowed and it always exits 0.

Debug: set SKILL_HOOK_DEBUG=1, pass --debug, or create hooks/debug.flag to store every raw payload in
~/.agents/dispatcher-data/hooks/debug-payloads/.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
DATA = HOME / ".agents" / "dispatcher-data"
HOOK_DIR = Path(os.environ.get("SKILL_HOOK_DIR", DATA / "hooks"))  # overridable for tests
STATE = HOOK_DIR / "state.json"
LOGGER = Path(os.environ.get("SKILL_HOOK_LOGGER",
                             HOME / ".agents" / "skills" / "skill-dispatcher" / "scripts" / "dispatch_logger.py"))
SKILL_ROOTS = [HOME / d for d in (".agents/skills", ".claude/skills", ".codex/skills", ".gemini/skills",
                                  ".gemini/antigravity/skills", ".gemini/config/skills", ".grok/skills",
                                  ".cursor/skills")]
DEDUPE_SECONDS = 30 * 60
SKILL_TOOLS = {"skill": "skill", "activate_skill": "name", "use_skill": "name", "load_skill": "name"}
# <home>/.<harness>/.../skills/<name>/.../SKILL.md  (also plugin caches such as ~/.codex/plugins/cache/.../skills/pdf)
SKILL_PATH = re.compile(r"[\\/]\.(?:agents|claude|codex|gemini|grok|cursor)[\\/](?:[^\\/'\"\s]+[\\/])*?skills[\\/]"
                        r"(?P<name>[A-Za-z0-9._-]+)[\\/](?:(?P<sub>[^'\"\s]*?)[\\/])?SKILL\.md", re.IGNORECASE)
PROMPT_SLASH = re.compile(r"^\s*/(?:(?:user|local|repo):)?(?P<name>[A-Za-z0-9._-]+)")
PROMPT_DOLLAR = re.compile(r"(?<![\w$])\$(?P<name>[A-Za-z][A-Za-z0-9._-]+)")


def installed_skills():
    names = set()
    for root in SKILL_ROOTS:
        try:
            names.update(p.name.lower() for p in root.iterdir() if (p / "SKILL.md").is_file())
        except OSError:
            pass
    return names


def first(d, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return default


def model_from_transcript(path):
    """Newest model name in a Claude (JSONL) or Gemini (JSON/JSONL) transcript."""
    if not path:
        return None
    try:
        p = Path(path)
        data = p.read_bytes()[-400_000:].decode("utf-8", errors="replace")
    except OSError:
        return None
    hits = re.findall(r'"model"\s*:\s*"([^"<>]{3,80})"', data)
    hits = [h for h in hits if h not in ("<synthetic>",)]
    return hits[-1] if hits else None


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state):
    cutoff = time.time() - 3 * 86400
    state = {s: v for s, v in state.items() if v.get("touched", 0) > cutoff}
    HOOK_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    os.replace(tmp, STATE)


def detect_from_tool(tool, tool_input, skills):
    """Return [(skill, how)] for a tool event."""
    found = []
    key = SKILL_TOOLS.get((tool or "").lower())
    if key and isinstance(tool_input, dict):
        name = str(tool_input.get(key) or tool_input.get("name") or "").strip().split(":")[-1]
        if name:
            found.append((name, f"{tool} tool"))
    text = json.dumps(tool_input, ensure_ascii=False) if not isinstance(tool_input, str) else tool_input
    text = text.replace("\\\\", "\\")
    for m in SKILL_PATH.finditer(text):
        how = f"{tool} read SKILL.md" + (f" ({m.group('sub')})" if m.group("sub") else "")
        found.append((m.group("name"), how))
    return [(n, h) for n, h in found if n.lower() in skills]


def detect_from_prompt(prompt, harness, skills):
    if not isinstance(prompt, str):
        return []
    found = []
    m = PROMPT_SLASH.match(prompt)
    if m and m.group("name").lower() in skills:
        found.append((m.group("name"), "user /command"))
    if harness == "codex":
        found += [(m.group("name"), "user $mention") for m in PROMPT_DOLLAR.finditer(prompt)
                  if m.group("name").lower() in skills]
    return found


def log_event(harness, skill, how, event, model, session):
    cmd = [sys.executable, str(LOGGER), "--skill", skill,
           "--intent", f"skill used (via {harness} hook)",
           "--reason", f"hook:{harness} {event}: {how}",
           "--decision", "HANDOFF",
           "--chain-id", f"{harness[:6]}-{str(session)[:8]}"]
    if model:
        cmd += ["--model", model]
    env = dict(os.environ, SKILL_DISPATCH_AUTO_POLICY_LOOKUP="0")
    subprocess.run(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--harness", required=True, choices=["claude-code", "codex", "gemini", "antigravity", "grok"])
    ap.add_argument("--event", help="event name, for harnesses whose payload omits it (Antigravity)")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()
    raw = sys.stdin.read()
    if args.harness == "claude-code" and os.environ.get("GROK_HOOK_EVENT"):
        return  # Grok also executes ~/.claude/settings.json hooks; its own registration handles Grok.
    payload = json.loads(raw) if raw.strip() else {}
    if args.debug or os.environ.get("SKILL_HOOK_DEBUG") == "1" or (HOOK_DIR / "debug.flag").exists():
        try:  # a debugging aid must never stop the logging itself
            dbg = HOOK_DIR / "debug-payloads"
            dbg.mkdir(parents=True, exist_ok=True)
            (dbg / f"{args.harness}-{time.time_ns()}.json").write_text(raw[:200_000], encoding="utf-8")
        except OSError:
            pass

    call = payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else {}  # Antigravity shape
    event = args.event or first(payload, "hook_event_name", "hookEventName", default="?")
    session = first(payload, "session_id", "sessionId", "conversationId",
                    default=os.environ.get("GROK_SESSION_ID", "nosession"))
    tool = first(payload, "tool_name", "toolName") or call.get("name")
    tool_input = first(payload, "tool_input", "toolInput", default=None) or call.get("args") or {}
    model = first(payload, "model", "modelId", "model_name", "modelName") or \
        model_from_transcript(first(payload, "transcript_path", "transcriptPath"))

    skills = installed_skills()
    state = load_state()
    sess = state.setdefault(str(session), {"logged": {}, "pending": []})
    sess["touched"] = time.time()

    hits = []
    if tool:
        hits = detect_from_tool(tool, tool_input, skills)
    elif event in ("UserPromptSubmit", "BeforeAgent", "user_prompt_submit"):
        hits = detect_from_prompt(first(payload, "prompt", "userPrompt", "user_prompt"), args.harness, skills)
        if hits and not model:  # model unknown before the first reply: log at turn end
            sess["pending"] += [[n, h, event] for n, h in hits]
            hits = []

    if model or event in ("Stop", "AfterAgent", "stop", "SessionEnd"):
        hits += [(n, h, e) for n, h, e in sess.get("pending", [])]
        sess["pending"] = []
    now = time.time()
    for hit in hits:
        name, how = hit[0], hit[1]
        ev = hit[2] if len(hit) > 2 else event
        last = sess["logged"].get(name.lower(), 0)
        if now - last < DEDUPE_SECONDS:
            continue
        sess["logged"][name.lower()] = now
        log_event(args.harness, name, how, ev, model, session)
    save_state(state)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # never break the harness
        try:
            HOOK_DIR.mkdir(parents=True, exist_ok=True)
            with open(HOOK_DIR / "errors.log", "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {sys.argv[1:]} {exc!r}\n")
        except Exception:
            pass
    if "--harness" in sys.argv and "gemini" in sys.argv:
        print("{}")
    sys.exit(0)
