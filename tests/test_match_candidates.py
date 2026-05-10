"""Unit tests for match_candidates.py."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import match_candidates


class TestIntentParsing(unittest.TestCase):
    def test_layer_preference_from_audit_intent(self):
        assert match_candidates._intent_layer_preference("audit_skill_frontmatter") == "feedback"

    def test_layer_preference_from_build_intent(self):
        assert match_candidates._intent_layer_preference("build_new_feature") == "execution"

    def test_layer_preference_from_load_intent(self):
        assert match_candidates._intent_layer_preference("load_personal_context") == "information"

    def test_layer_preference_unknown_verb(self):
        assert match_candidates._intent_layer_preference("foobar_something") == ""

    def test_intent_keywords(self):
        assert match_candidates._intent_keywords("audit_skill_frontmatter") == {"audit", "skill", "frontmatter"}


class TestScoring(unittest.TestCase):
    def _skill(self, **overrides):
        defaults = {
            "name": "test-skill",
            "description": "Test skill description",
            "accepted_intents": [],
            "capabilities": [],
            "stack_tags": [],
            "input_artifacts": [],
            "output_artifacts": [],
            "layer": "execution",
            "risk": "low",
            "lifecycle": "active",
        }
        defaults.update(overrides)
        return defaults

    def test_exact_intent_match_scores_5(self):
        skill = self._skill(accepted_intents=["audit_code"])
        result = match_candidates.score_skill(skill, "audit_code", [], [], "", "")
        assert result["score"] == 5
        assert "audit_code" in result["breakdown"]["accepted_intents"]

    def test_partial_intent_keyword_match_scores_1(self):
        skill = self._skill(accepted_intents=["run_audit"])
        result = match_candidates.score_skill(skill, "audit_code", [], [], "", "")
        # 'audit' is in 'run_audit' as a partial match: +1
        assert result["score"] == 1

    def test_capability_match_scores_3_per_match(self):
        skill = self._skill(capabilities=["accessibility-audit", "wcag-review"])
        result = match_candidates.score_skill(skill, "audit_accessibility", [], [], "", "")
        # 'audit' matches 'accessibility-audit' (cap_words has audit) -> +3
        # 'accessibility' matches 'accessibility-audit' (cap_words has accessibility) -> already matched, only counted once per cap
        # 'wcag-review' doesn't have any of audit/accessibility keywords -> no match
        assert result["score"] >= 3

    def test_stack_tags_overlap_scores_2(self):
        skill = self._skill(stack_tags=["angular", "typescript"])
        result = match_candidates.score_skill(skill, "build_ui", [], ["angular"], "", "")
        assert result["breakdown"]["stack_tags"] == ["angular"]
        # +1 layer (build -> execution) +2 stack(angular) = 3
        assert result["score"] >= 2

    def test_input_artifact_match(self):
        skill = self._skill(input_artifacts=["bug_report"])
        result = match_candidates.score_skill(skill, "fix", [], [], "bug_report", "")
        assert "bug_report" in result["breakdown"]["input_artifacts"]
        assert result["score"] >= 2

    def test_layer_alignment_bonus(self):
        skill = self._skill(layer="feedback")
        result = match_candidates.score_skill(skill, "audit_code", [], [], "", "")
        # audit -> feedback layer alignment = +1
        assert result["breakdown"]["layer_alignment"] == 1

    def test_zero_score_when_nothing_matches(self):
        skill = self._skill(
            accepted_intents=["unrelated_intent"],
            capabilities=["unrelated-thing"],
            stack_tags=["python"],
            description="Nothing relevant",
        )
        result = match_candidates.score_skill(skill, "audit_xyz", [], [], "", "")
        # No matches at all, layer wrong, no description match => 0
        assert result["score"] == 0


class TestFiltering(unittest.TestCase):
    def test_archived_skill_filtered_out(self):
        skills = {
            "active-skill": {"name": "active-skill", "lifecycle": "active", "risk": "low"},
            "archived-skill": {"name": "archived-skill", "lifecycle": "archived", "risk": "low"},
        }
        kept, filtered = match_candidates.filter_candidates(skills, "high")
        assert "active-skill" in kept
        assert "archived-skill" not in kept
        assert any(f["skill"] == "archived-skill" and "archived" in f["reason"] for f in filtered)

    def test_dispatcher_never_routes_to_itself(self):
        skills = {
            "skill-dispatcher": {"name": "skill-dispatcher", "lifecycle": "active", "risk": "low"},
            "other-skill": {"name": "other-skill", "lifecycle": "active", "risk": "low"},
        }
        kept, filtered = match_candidates.filter_candidates(skills, "high")
        assert "skill-dispatcher" not in kept
        assert "other-skill" in kept

    def test_high_risk_filtered_when_max_is_low(self):
        skills = {
            "low-skill": {"name": "low-skill", "lifecycle": "active", "risk": "low"},
            "high-skill": {"name": "high-skill", "lifecycle": "active", "risk": "high"},
        }
        kept, filtered = match_candidates.filter_candidates(skills, "low")
        assert "low-skill" in kept
        assert "high-skill" not in kept


class TestEndToEnd(unittest.TestCase):
    def test_returns_top_n_sorted_descending(self):
        """Build a tiny registry and verify top-N candidate ordering."""
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "SKILL_REGISTRY.json"
            payload = {
                "skills": [
                    {
                        "name": "perfect-match",
                        "accepted_intents": ["audit_code"],
                        "capabilities": ["audit"],
                        "stack_tags": ["python"],
                        "layer": "feedback",
                        "risk": "low",
                        "lifecycle": "active",
                    },
                    {
                        "name": "partial-match",
                        "accepted_intents": ["run_audit"],
                        "capabilities": [],
                        "stack_tags": [],
                        "layer": "feedback",
                        "risk": "low",
                        "lifecycle": "active",
                    },
                    {
                        "name": "no-match",
                        "accepted_intents": ["unrelated"],
                        "capabilities": [],
                        "stack_tags": [],
                        "layer": "execution",
                        "risk": "low",
                        "lifecycle": "active",
                    },
                ]
            }
            registry.write_text(json.dumps(payload), encoding="utf-8")

            old_argv = sys.argv
            sys.argv = [
                "match_candidates.py",
                "--intent", "audit_code",
                "--top-n", "3",
                "--registry", str(registry),
                "--format", "json",
            ]
            from io import StringIO
            captured = StringIO()
            try:
                with patch("sys.stdout", captured):
                    rc = match_candidates.main()
            finally:
                sys.argv = old_argv

            assert rc == 0
            output = json.loads(captured.getvalue())
            names = [c["skill"] for c in output["candidates"]]
            # perfect-match must rank above partial-match
            assert names.index("perfect-match") < names.index("partial-match")
            # no-match has score 0 so should not appear
            assert "no-match" not in names

    def test_no_candidates_returns_empty_list(self):
        """Registry with only archived skills should return zero candidates."""
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "SKILL_REGISTRY.json"
            payload = {
                "skills": [
                    {"name": "archived-only", "lifecycle": "archived", "risk": "low"},
                ]
            }
            registry.write_text(json.dumps(payload), encoding="utf-8")

            old_argv = sys.argv
            sys.argv = ["match_candidates.py", "--intent", "anything",
                        "--registry", str(registry), "--format", "json"]
            from io import StringIO
            captured = StringIO()
            try:
                with patch("sys.stdout", captured):
                    rc = match_candidates.main()
            finally:
                sys.argv = old_argv

            assert rc == 0
            output = json.loads(captured.getvalue())
            assert output["candidates"] == []
            assert output["after_gates"] == 0


if __name__ == "__main__":
    unittest.main()
