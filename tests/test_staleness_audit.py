import importlib.util
import unittest
from collections import Counter
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parent.parent / "scripts" / "staleness_audit.py"


def load_module():
    spec = importlib.util.spec_from_file_location("skill_dispatcher_staleness_audit", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class StalenessAuditTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_extract_logged_skills_prefers_explicit_skills_used(self):
        event = {
            "selected_skill": "analysis-skill",
            "skills_used": ["analysis-skill", "playwright-skill"],
        }

        self.assertEqual(
            self.module.extract_logged_skills(event),
            ["analysis-skill", "playwright-skill"],
        )

    def test_extract_logged_skills_supports_legacy_sequence_strings(self):
        event = {"selected_skill": "analysis-skill + playwright-skill & doc-skill"}

        self.assertEqual(
            self.module.extract_logged_skills(event),
            ["analysis-skill", "playwright-skill", "doc-skill"],
        )

    def test_usage_counter_counts_every_skill_in_sequence(self):
        events = [
            {"selected_skill": "analysis-skill", "skills_used": ["analysis-skill", "playwright-skill"]},
            {"selected_skill": "playwright-skill"},
        ]

        usage = Counter()
        for event in events:
            for skill in self.module.extract_logged_skills(event):
                usage[skill] += 1

        self.assertEqual(usage["analysis-skill"], 1)
        self.assertEqual(usage["playwright-skill"], 2)


if __name__ == "__main__":
    unittest.main()
