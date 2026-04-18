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


if __name__ == "__main__":
    unittest.main()
