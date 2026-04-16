import subprocess
import sys
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


if __name__ == "__main__":
    unittest.main()
