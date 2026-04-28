import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LOGGER = ROOT / "scripts" / "dispatch_logger.py"


class DispatchLoggerTests(unittest.TestCase):
    def test_sequence_requires_skills_argument(self):
        result = subprocess.run(
            [
                sys.executable,
                str(LOGGER),
                "--skill",
                "analysis-skill",
                "--intent",
                "test_sequence_contract",
                "--reason",
                "regression",
                "--decision",
                "SEQUENCE",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--skills is required when --decision SEQUENCE is used.", result.stderr)

    def test_sequence_with_skills_succeeds(self):
        result = subprocess.run(
            [
                sys.executable,
                str(LOGGER),
                "--skill",
                "analysis-skill",
                "--skills",
                "analysis-skill, playwright-skill",
                "--intent",
                "test_sequence_contract",
                "--reason",
                "regression",
                "--decision",
                "SEQUENCE",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_logger_captures_policy_lookup_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "dispatch_events.jsonl"
            config_path = Path(temp_dir) / "settings.json"
            config_path.write_text('{"logging_enabled": true}', encoding="utf-8")

            env = os.environ.copy()
            env["SKILL_DISPATCH_LOG_PATH"] = str(log_path)
            env["SKILL_DISPATCH_CONFIG_PATH"] = str(config_path)
            env["SKILL_DISPATCH_DISABLE_WALLBOARD"] = "1"

            result = subprocess.run(
                [
                    sys.executable,
                    str(LOGGER),
                    "--skill",
                    "playwright-skill",
                    "--intent",
                    "implement_ui_confirmation_test",
                    "--reason",
                    "Shared and project policy context was consulted",
                    "--decision",
                    "HANDOFF",
                    "--policy-topic",
                    "RoutingPolicies",
                    "--policy-status",
                    "hit",
                    "--policy-source",
                    "both",
                    "--policy-hit-count",
                    "2",
                    "--policy-applied",
                    "true",
                    "--policy-changed-routing",
                    "true",
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(payload["policy_lookup"]["status"], "hit")
            self.assertEqual(payload["policy_lookup"]["source"], "both")
            self.assertEqual(payload["policy_lookup"]["hit_count"], 2)
            self.assertTrue(payload["policy_lookup"]["applied"])
            self.assertTrue(payload["policy_lookup"]["changed_routing"])

    def test_logger_captures_model_from_argument(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "dispatch_events.jsonl"
            config_path = Path(temp_dir) / "settings.json"
            config_path.write_text('{"logging_enabled": true}', encoding="utf-8")

            env = os.environ.copy()
            env["SKILL_DISPATCH_LOG_PATH"] = str(log_path)
            env["SKILL_DISPATCH_CONFIG_PATH"] = str(config_path)
            env["SKILL_DISPATCH_DISABLE_WALLBOARD"] = "1"
            env["SKILL_DISPATCH_AUTO_POLICY_LOOKUP"] = "0"

            result = subprocess.run(
                [
                    sys.executable,
                    str(LOGGER),
                    "--skill",
                    "playwright-skill",
                    "--intent",
                    "implement_ui_confirmation_test",
                    "--reason",
                    "model telemetry regression",
                    "--decision",
                    "HANDOFF",
                    "--model",
                    "gpt-5.5",
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(payload["model"], "gpt-5.5")

    def test_logger_captures_codex_runtime_as_model_when_no_model_is_exposed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "dispatch_events.jsonl"
            config_path = Path(temp_dir) / "settings.json"
            config_path.write_text('{"logging_enabled": true}', encoding="utf-8")

            env = os.environ.copy()
            env["SKILL_DISPATCH_LOG_PATH"] = str(log_path)
            env["SKILL_DISPATCH_CONFIG_PATH"] = str(config_path)
            env["SKILL_DISPATCH_DISABLE_WALLBOARD"] = "1"
            env["SKILL_DISPATCH_AUTO_POLICY_LOOKUP"] = "0"
            env["CODEX_INTERNAL_ORIGINATOR_OVERRIDE"] = "codex_vscode"
            for key in ("SKILL_DISPATCH_MODEL", "AGENT_MODEL", "CODEX_MODEL", "OPENAI_MODEL"):
                env.pop(key, None)

            result = subprocess.run(
                [
                    sys.executable,
                    str(LOGGER),
                    "--skill",
                    "playwright-skill",
                    "--intent",
                    "implement_ui_confirmation_test",
                    "--reason",
                    "codex runtime model regression",
                    "--decision",
                    "HANDOFF",
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(payload["model"], "Codex")

    def test_logger_auto_populates_policy_lookup_when_flags_are_omitted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            repo_root = temp_root / "demo-repo"
            repo_root.mkdir(parents=True)
            (repo_root / ".git").mkdir()

            log_path = temp_root / "dispatch_events.jsonl"
            config_path = temp_root / "settings.json"
            shared_memory_file = temp_root / "shared_memory.json"
            config_path.write_text('{"logging_enabled": true}', encoding="utf-8")
            shared_memory_file.write_text(
                json.dumps(
                    {
                        "schema_version": "2.0",
                        "topics": {
                            "RoutingPolicies": [
                                {
                                    "id": 1,
                                    "status": "active",
                                    "created_at": "2026-04-11T00:00:00Z",
                                    "last_reviewed_at": "2026-04-11T00:00:00Z",
                                    "review_after_days": 365,
                                    "source": "UnitTest",
                                    "confidence": 0.95,
                                    "content": "Load codebase-context before high-risk repo work.",
                                    "tags": ["routing"],
                                }
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["SKILL_DISPATCH_LOG_PATH"] = str(log_path)
            env["SKILL_DISPATCH_CONFIG_PATH"] = str(config_path)
            env["SKILL_DISPATCH_DISABLE_WALLBOARD"] = "1"
            env["AGENT_SHARED_MEMORY_PATH"] = str(shared_memory_file)

            result = subprocess.run(
                [
                    sys.executable,
                    str(LOGGER),
                    "--skill",
                    "playwright-skill",
                    "--intent",
                    "implement_ui_confirmation_test",
                    "--reason",
                    "Automatic policy telemetry should be attached",
                    "--decision",
                    "HANDOFF",
                ],
                cwd=repo_root,
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(payload["policy_lookup"]["status"], "hit")
            self.assertEqual(payload["policy_lookup"]["source"], "shared-memory")
            self.assertEqual(payload["policy_lookup"]["hit_count"], 1)
            self.assertFalse(payload["policy_lookup"]["applied"])


if __name__ == "__main__":
    unittest.main()
