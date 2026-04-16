import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "build_registry.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("skill_dispatcher_build_registry", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class BuildRegistryTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_parse_frontmatter_supports_block_lists(self):
        content = """---
name: sample-skill
description: Sample router target
metadata:
  author: demo
  version: "1.0.0"
  dispatcher-category: testing
  dispatcher-capabilities: test-design, review
  dispatcher-accepted-intents: design_confirmation_tests
  dispatcher-input-artifacts: bug_report
  dispatcher-output-artifacts: normalized_test_case
  dispatcher-writes-files: true
  dispatcher-manual-only: false
---
"""

        metadata = self.module.parse_frontmatter(content)

        self.assertEqual(metadata["name"], "sample-skill")
        self.assertEqual(metadata["metadata"]["dispatcher-capabilities"], "test-design, review")
        self.assertEqual(metadata["metadata"]["dispatcher-accepted-intents"], "design_confirmation_tests")
        self.assertEqual(metadata["metadata"]["dispatcher-input-artifacts"], "bug_report")
        self.assertEqual(metadata["metadata"]["dispatcher-output-artifacts"], "normalized_test_case")
        self.assertTrue(metadata["metadata"]["dispatcher-writes-files"])
        self.assertFalse(metadata["metadata"]["dispatcher-manual-only"])

    def test_find_skills_normalizes_capability_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir) / "test-design-orchestrator"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                """---
name: test-design-orchestrator
description: Design tests from requirements.
metadata:
  author: demo
  version: "1.0.0"
  dispatcher-category: testing
  dispatcher-capabilities: test-design
  dispatcher-accepted-intents: design_confirmation_tests
  dispatcher-input-artifacts: bug_report
  dispatcher-output-artifacts: normalized_test_case
  dispatcher-stack-tags: playwright, cypress
  dispatcher-writes-files: false
  dispatcher-manual-only: false
---
""",
                encoding="utf-8",
            )

            skills = self.module.find_skills([Path(temp_dir)])
            metadata = skills["test-design-orchestrator"]["metadata"]

            self.assertEqual(metadata["category"], "testing")
            self.assertEqual(metadata["capabilities"], ["test-design"])
            self.assertEqual(metadata["accepted_intents"], ["design_confirmation_tests"])
            self.assertEqual(metadata["input_artifacts"], ["bug_report"])
            self.assertEqual(metadata["output_artifacts"], ["normalized_test_case"])
            self.assertEqual(metadata["stack_tags"], ["playwright", "cypress"])
            self.assertFalse(metadata["writes_files"])
            self.assertFalse(metadata["manual_only"])

    def test_json_registry_contains_capability_and_intent_indexes(self):
        generated_at = self.module.datetime.datetime(2026, 4, 8, 12, 0, 0)
        skills = {
            "playwright-skill": {
                "name": "playwright-skill",
                "path": "C:/skills/playwright-skill",
                "source": "C:/skills",
                "metadata": {
                    "description": "Playwright automation.",
                    "category": "testing",
                    "risk": "medium",
                    "tags": ["playwright"],
                    "capabilities": ["ui-automation"],
                    "accepted_intents": ["implement_ui_confirmation_test"],
                    "input_artifacts": ["normalized_test_case"],
                    "output_artifacts": ["automated_test"],
                    "stack_tags": ["playwright"],
                    "writes_files": True,
                    "manual_only": False,
                },
            }
        }

        capability_index, intent_index = self.module.build_indexes(skills)
        payload = self.module.render_json_registry(
            skills,
            [Path("C:/skills")],
            generated_at,
            capability_index,
            intent_index,
        )

        self.assertEqual(payload["capability_index"]["ui-automation"], ["playwright-skill"])
        self.assertEqual(
            payload["intent_index"]["implement_ui_confirmation_test"],
            ["playwright-skill"],
        )
        self.assertEqual(
            payload["dispatch_contract"]["inputs"],
            [
                "intent",
                "current_artifact_type",
                "target_artifact_type",
                "repo_context",
                "constraints",
                "preferred_stack",
                "allowed_write_risk",
            ],
        )


if __name__ == "__main__":
    unittest.main()
