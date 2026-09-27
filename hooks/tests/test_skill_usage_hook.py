"""Offline tests for skill_usage_hook.py: synthetic payloads in each harness's real format.

The hook runs as a subprocess (as the harness would run it) with SKILL_HOOK_DIR pointing at a temp
dir and SKILL_HOOK_LOGGER at a stub, so nothing reaches the real dispatch log, wallboard or Honcho.
Payload shapes come from probe runs and session transcripts captured on 2026-09-26.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "skill_usage_hook.py"
HOME = Path.home()
SKILL = "booklet-droodle"  # installed in ~/.agents/skills and linked into every harness
RT_SKILL_MD = str(HOME / ".agents" / "skills" / SKILL / "SKILL.md")
STUB = 'import json,sys,os\nopen(os.environ["STUB_OUT"],"a",encoding="utf-8").write(json.dumps(sys.argv[1:])+"\\n")\n'


class HookTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "stub_logger.py").write_text(STUB, encoding="utf-8")
        self.out = self.tmp / "calls.jsonl"
        self.env = dict(os.environ, SKILL_HOOK_DIR=str(self.tmp / "hooks"), SKILL_HOOK_LOGGER=str(self.tmp / "stub_logger.py"),
                        STUB_OUT=str(self.out))
        self.env.pop("GROK_HOOK_EVENT", None)

    def run_hook(self, harness, payload, extra_env=None):
        env = dict(self.env, **(extra_env or {}))
        data = payload if isinstance(payload, str) else json.dumps(payload)
        r = subprocess.run([sys.executable, str(HOOK), "--harness", harness], input=data, capture_output=True,
                           text=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def calls(self):
        if not self.out.exists():
            return []
        return [json.loads(l) for l in self.out.read_text(encoding="utf-8").splitlines() if l.strip()]

    @staticmethod
    def arg(call, flag):
        return call[call.index(flag) + 1] if flag in call else None

    def transcript(self, model):
        p = self.tmp / f"t-{model}.jsonl"
        p.write_text(json.dumps({"type": "assistant", "message": {"model": model, "content": []}}) + "\n", encoding="utf-8")
        return str(p)

    # --- Claude Code -------------------------------------------------------------------------
    def test_claude_skill_tool(self):
        self.run_hook("claude-code", {"hook_event_name": "PostToolUse", "session_id": "c1", "tool_name": "Skill",
                                      "tool_input": {"skill": SKILL}, "transcript_path": self.transcript("claude-haiku-4-5")})
        c = self.calls()
        self.assertEqual(len(c), 1)
        self.assertEqual(self.arg(c[0], "--skill"), SKILL)
        self.assertEqual(self.arg(c[0], "--model"), "claude-haiku-4-5")
        self.assertIn("claude-code hook", self.arg(c[0], "--intent"))

    def test_claude_dedupes_within_session(self):
        base = {"hook_event_name": "PostToolUse", "session_id": "c2", "transcript_path": self.transcript("m")}
        self.run_hook("claude-code", dict(base, tool_name="Skill", tool_input={"skill": SKILL}))
        self.run_hook("claude-code", dict(base, tool_name="Read", tool_input={"file_path": RT_SKILL_MD}))
        self.assertEqual(len(self.calls()), 1)

    def test_claude_read_of_runtime_skill_md(self):
        self.run_hook("claude-code", {"hook_event_name": "PostToolUse", "session_id": "c3", "tool_name": "Read",
                                      "tool_input": {"file_path": RT_SKILL_MD}, "transcript_path": self.transcript("m")})
        self.assertEqual([self.arg(c, "--skill") for c in self.calls()], [SKILL])

    def test_dev_tree_read_is_not_usage(self):
        self.run_hook("claude-code", {"hook_event_name": "PostToolUse", "session_id": "c4", "tool_name": "Read",
                                      "tool_input": {"file_path": rf"C:\projects\skills\{SKILL}\SKILL.md"}})
        self.assertEqual(self.calls(), [])

    def test_claude_slash_command_logged_at_stop_with_model(self):
        self.run_hook("claude-code", {"hook_event_name": "UserPromptSubmit", "session_id": "c5",
                                      "prompt": f"/{SKILL} make a chapter image"})
        self.assertEqual(self.calls(), [], "no model yet -> pending")
        self.run_hook("claude-code", {"hook_event_name": "Stop", "session_id": "c5",
                                      "transcript_path": self.transcript("claude-opus-5-5")})
        c = self.calls()
        self.assertEqual(len(c), 1)
        self.assertEqual(self.arg(c[0], "--model"), "claude-opus-5-5")
        self.assertIn("user /command", self.arg(c[0], "--reason"))

    def test_claude_registration_ignored_inside_grok(self):
        self.run_hook("claude-code", {"hook_event_name": "PostToolUse", "sessionId": "g0", "toolName": "read_file",
                                      "toolInput": {"path": RT_SKILL_MD}}, extra_env={"GROK_HOOK_EVENT": "post_tool_use"})
        self.assertEqual(self.calls(), [])

    # --- Codex ------------------------------------------------------------------------------
    def test_codex_shell_read(self):
        self.run_hook("codex", {"hook_event_name": "PostToolUse", "session_id": "x1", "model": "gpt-5.6-sol",
                                "tool_name": "Bash", "tool_input": {"command": f"Get-Content -Raw '{RT_SKILL_MD}'"}})
        c = self.calls()
        self.assertEqual([self.arg(x, "--skill") for x in c], [SKILL])
        self.assertEqual(self.arg(c[0], "--model"), "gpt-5.6-sol")

    def test_codex_dollar_mention(self):
        self.run_hook("codex", {"hook_event_name": "UserPromptSubmit", "session_id": "x2", "model": "gpt-5.6-sol",
                                "prompt": f"please use ${SKILL} for the intro slide"})
        self.assertEqual([self.arg(x, "--skill") for x in self.calls()], [SKILL])

    def test_codex_dollar_mention_followed_by_punctuation(self):
        """Regression (2026-09-27 live run): 'Use $booklet-droodle.' was read as 'booklet-droodle.'."""
        self.run_hook("codex", {"hook_event_name": "UserPromptSubmit", "session_id": "x4", "model": "gpt-5.6-sol",
                                "prompt": f"Use ${SKILL}. Do not generate any image."})
        self.assertEqual([self.arg(x, "--skill") for x in self.calls()], [SKILL])

    def test_codex_invalid_utf8_in_payload_still_logs(self):
        """Regression (2026-09-27, Codex app): a web-tool result with invalid UTF-8 crashed the debug dump."""
        payload = json.dumps({"hook_event_name": "PostToolUse", "session_id": "x5", "model": "gpt-5.6-sol",
                              "tool_name": "webrun",
                              "tool_input": {"open": [{"ref_id": f"file:///{RT_SKILL_MD.replace(chr(92), '/')}"}]},
                              "tool_response": "PLACEHOLDER"}).encode("utf-8")
        payload = payload.replace(b"PLACEHOLDER", b"bad \xed\xb3\x81 bytes")  # an encoded lone surrogate
        hooks = self.tmp / "hooks"
        hooks.mkdir()
        (hooks / "debug.flag").write_text("", encoding="utf-8")
        r = subprocess.run([sys.executable, str(HOOK), "--harness", "codex"], input=payload, capture_output=True,
                           env=self.env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([self.arg(x, "--skill") for x in self.calls()], [SKILL])
        self.assertFalse((hooks / "errors.log").exists())

    def test_codex_stop_scans_only_recorded_tool_calls(self):
        """Codex fires no PostToolUse for a hung command; its transcript also lists every skill's path."""
        other = str(HOME / ".agents" / "skills" / "sketchy-slides" / "SKILL.md")
        lines = [
            {"type": "response_item", "payload": {"type": "message", "role": "developer",
                                                  "content": [{"type": "input_text", "text": f"Skills: {other} {RT_SKILL_MD}"}]}},
            {"type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec",
                                                  "input": f"const r = await tools.exec_command({{cmd:\"Get-Content -Raw '{RT_SKILL_MD}'\"}});"}},
        ]
        t = self.tmp / "rollout.jsonl"
        t.write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
        stop = {"hook_event_name": "Stop", "session_id": "x6", "model": "gpt-5.6-sol", "transcript_path": str(t)}
        self.run_hook("codex", stop)
        c = self.calls()
        self.assertEqual([self.arg(x, "--skill") for x in c], [SKILL], "sketchy-slides is only listed, not read")
        self.assertIn("(transcript)", self.arg(c[0], "--reason"))

    def test_nested_sub_skill_maps_to_parent(self):
        p = HOME / ".agents" / "skills" / "playwright-skill" / "core" / "SKILL.md"
        self.run_hook("codex", {"hook_event_name": "PostToolUse", "session_id": "x3", "model": "gpt-5.6-sol",
                                "tool_name": "Bash", "tool_input": {"command": f"cat '{p}'"}})
        c = self.calls()
        self.assertEqual([self.arg(x, "--skill") for x in c], ["playwright-skill"])
        self.assertIn("(core)", self.arg(c[0], "--reason"))

    # --- Gemini -----------------------------------------------------------------------------
    def test_gemini_activate_skill_prints_json(self):
        t = self.tmp / "gemini.jsonl"
        t.write_text('{"type":"gemini","model":"gemini-3-flash-preview"}\n', encoding="utf-8")
        out = self.run_hook("gemini", {"hook_event_name": "AfterTool", "session_id": "m1", "tool_name": "activate_skill",
                                       "tool_input": {"name": SKILL}, "transcript_path": str(t)})
        self.assertEqual(out.strip(), "{}")
        c = self.calls()
        self.assertEqual(self.arg(c[0], "--skill"), SKILL)
        self.assertEqual(self.arg(c[0], "--model"), "gemini-3-flash-preview")

    def test_unknown_skill_is_ignored(self):
        self.run_hook("gemini", {"hook_event_name": "AfterTool", "session_id": "m2", "tool_name": "activate_skill",
                                 "tool_input": {"name": "no-such-skill-xyz"}})
        self.assertEqual(self.calls(), [])

    # --- Antigravity (Gemini IDE / agy) ------------------------------------------------------
    def test_antigravity_view_file_with_event_flag(self):
        env = dict(self.env)
        payload = {"conversationId": "a1", "modelName": "gemini-3.1-pro", "transcriptPath": "",
                   "toolCall": {"name": "view_file", "args": {"AbsolutePath": RT_SKILL_MD}}, "stepIdx": 3}
        r = subprocess.run([sys.executable, str(HOOK), "--harness", "antigravity", "--event", "PostToolUse"],
                           input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "{}", "Antigravity requires a JSON object on stdout")
        c = self.calls()
        self.assertEqual([self.arg(x, "--skill") for x in c], [SKILL])
        self.assertEqual(self.arg(c[0], "--model"), "gemini-3.1-pro")
        self.assertIn("antigravity hook", self.arg(c[0], "--intent"))

    def test_antigravity_stop_scans_new_transcript_lines_once(self):
        t = self.tmp / "transcript.jsonl"
        step = {"type": "PLANNER_RESPONSE", "tool_calls": [{"name": "view_file", "args": {"AbsolutePath": RT_SKILL_MD}}]}
        t.write_text(json.dumps(step) + "\n", encoding="utf-8")
        payload = {"conversationId": "a2", "modelName": "gemini-3.1-pro", "transcriptPath": str(t),
                   "executionNum": 1, "terminationReason": "model_stop"}

        def stop():
            r = subprocess.run([sys.executable, str(HOOK), "--harness", "antigravity", "--event", "Stop"],
                               input=json.dumps(payload), capture_output=True, text=True, env=self.env, timeout=60)
            self.assertEqual(r.stdout.strip(), "{}")

        stop()
        self.assertEqual([self.arg(x, "--skill") for x in self.calls()], [SKILL])
        self.assertIn("(transcript)", self.arg(self.calls()[0], "--reason"))
        stop()  # nothing new in the transcript -> no second event
        self.assertEqual(len(self.calls()), 1)

    def test_antigravity_transcript_with_nested_json_escaping(self):
        """Real Antigravity transcripts store args as JSON-in-JSON: the path has 4 backslashes per separator."""
        t = self.tmp / "transcript2.jsonl"
        inner = json.dumps(RT_SKILL_MD)  # "C:\\Users\\..."  (quoted, escaped once)
        step = {"tool_calls": [{"name": "view_file", "args": {"AbsolutePath": inner}}]}
        t.write_text(json.dumps(step) + "\n", encoding="utf-8")  # escaped twice on disk
        self.assertIn("\\\\\\\\", t.read_text(encoding="utf-8"))
        payload = {"conversationId": "a3", "modelName": "gemini-3.1-pro", "transcriptPath": str(t)}
        r = subprocess.run([sys.executable, str(HOOK), "--harness", "antigravity", "--event", "Stop"],
                           input=json.dumps(payload), capture_output=True, text=True, env=self.env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([self.arg(x, "--skill") for x in self.calls()], [SKILL])

    # --- Grok -------------------------------------------------------------------------------
    def test_grok_camelcase_read_file(self):
        t = self.tmp / "updates.jsonl"  # Grok's transcript: the only place its model name appears
        t.write_text('{"type":"turn","modelId":"grok-4.7","content":"x"}\n', encoding="utf-8")
        self.run_hook("grok", {"hook_event_name": "PostToolUse", "hookEventName": "post_tool_use", "sessionId": "k1",
                               "toolName": "read_file", "toolInput": {"path": RT_SKILL_MD},
                               "transcriptPath": str(t), "transcript_path": str(t)})
        c = self.calls()
        self.assertEqual([self.arg(x, "--skill") for x in c], [SKILL])
        self.assertEqual(self.arg(c[0], "--model"), "grok-4.7")

    # --- robustness -------------------------------------------------------------------------
    def test_debug_dump_failure_does_not_stop_logging(self):
        """Regression (2026-09-26): on Windows a DEBUG flag file collided with the debug/ folder."""
        hooks = self.tmp / "hooks"
        hooks.mkdir()
        (hooks / "debug.flag").write_text("", encoding="utf-8")
        (hooks / "debug-payloads").write_text("a file where the folder should be", encoding="utf-8")
        self.run_hook("claude-code", {"hook_event_name": "PostToolUse", "session_id": "d1", "tool_name": "Skill",
                                      "tool_input": {"skill": SKILL}, "transcript_path": self.transcript("m")})
        self.assertEqual([self.arg(x, "--skill") for x in self.calls()], [SKILL])

    # --- GitHub Copilot CLI (payload format from docs.github.com hooks reference; not live-tested) ----
    def run_event(self, harness, event, payload):
        r = subprocess.run([sys.executable, str(HOOK), "--harness", harness, "--event", event],
                           input=json.dumps(payload), capture_output=True, text=True, env=self.env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_copilot_view_logged_at_agent_stop_with_model(self):
        base = {"sessionId": "cp1", "timestamp": 1790000000000, "cwd": str(HOME)}
        self.run_event("copilot", "postToolUse", dict(base, toolName="view", toolArgs={"path": RT_SKILL_MD},
                                                      toolResult={"resultType": "success", "textResultForLlm": "..."}))
        self.assertEqual(self.calls(), [], "no model in postToolUse: wait for agentStop")
        self.run_event("copilot", "agentStop", dict(base, transcriptPath=self.transcript("gpt-5.6"), stopReason="end_turn"))
        c = self.calls()
        self.assertEqual([self.arg(x, "--skill") for x in c], [SKILL])
        self.assertEqual(self.arg(c[0], "--model"), "gpt-5.6")
        self.assertIn("copilot hook", self.arg(c[0], "--intent"))

    def test_copilot_skill_tool_with_json_text_args(self):
        base = {"sessionId": "cp2", "timestamp": 1790000000000, "cwd": str(HOME)}
        self.run_event("copilot", "postToolUse", dict(base, toolName="skill", toolArgs=json.dumps({"skill": SKILL})))
        self.run_event("copilot", "agentStop", dict(base, transcriptPath="", stopReason="end_turn"))
        self.assertEqual([self.arg(x, "--skill") for x in self.calls()], [SKILL])

    def test_copilot_slash_prompt(self):
        base = {"sessionId": "cp3", "timestamp": 1790000000000, "cwd": str(HOME)}
        self.run_event("copilot", "userPromptSubmitted", dict(base, prompt=f"/{SKILL} make a booklet"))
        self.run_event("copilot", "agentStop", dict(base, transcriptPath=self.transcript("claude-sonnet-5")))
        c = self.calls()
        self.assertEqual([self.arg(x, "--skill") for x in c], [SKILL])
        self.assertIn("userPromptSubmitted: user /command", self.arg(c[0], "--reason"))

    # --- Hermes Agent shell hooks (payload format from hermes-agent agent/shell_hooks.py) --------
    def test_hermes_skill_lifecycle_loaded_logged_at_session_end(self):
        lifecycle = {"hook_event_name": "on_skill_lifecycle", "tool_name": None, "tool_input": None,
                     "session_id": "", "cwd": str(HOME), "profile": "default",
                     "extra": {"action": "loaded", "skill_name": SKILL, "provenance": "external",
                               "task_id": "h1", "use_count": 3, "reused": True, "reuse_after_patch": False}}
        self.run_hook("hermes", lifecycle)
        self.assertEqual(self.calls(), [], "no model in on_skill_lifecycle: wait for on_session_end")
        self.run_hook("hermes", {"hook_event_name": "on_session_end", "tool_name": None, "tool_input": None,
                                 "session_id": "sess-9", "cwd": str(HOME), "profile": "default",
                                 "extra": {"task_id": "h1", "completed": True, "interrupted": False,
                                           "model": "anthropic/claude-sonnet-5", "platform": "cli"}})
        c = self.calls()
        self.assertEqual([self.arg(x, "--skill") for x in c], [SKILL])
        self.assertEqual(self.arg(c[0], "--model"), "anthropic/claude-sonnet-5")
        self.assertIn("skill loaded (external)", self.arg(c[0], "--reason"))
        self.assertEqual(self.arg(c[0], "--chain-id"), "hermes-h1")

    def test_hermes_other_lifecycle_actions_are_not_usage(self):
        for action in ("created", "patched", "installed", "archived"):
            self.run_hook("hermes", {"hook_event_name": "on_skill_lifecycle", "session_id": "",
                                     "extra": {"action": action, "skill_name": SKILL, "task_id": "h2"}})
        self.run_hook("hermes", {"hook_event_name": "on_session_end", "session_id": "s",
                                 "extra": {"task_id": "h2", "model": "m"}})
        self.assertEqual(self.calls(), [])

    def test_garbage_input_never_fails(self):
        self.run_hook("codex", "this is not json")
        self.assertEqual(self.calls(), [])
        self.assertTrue((self.tmp / "hooks" / "errors.log").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
