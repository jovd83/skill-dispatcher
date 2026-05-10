import unittest

from scripts.generate_wallboard import (
    extract_model_name,
    infer_model_vendor,
    render_html,
    render_model_badge,
    render_model_count_row,
    render_recent_activity,
    simple_icon_url,
)


class GenerateWallboardTests(unittest.TestCase):
    def test_recent_activity_renders_model_column_badge(self):
        event = {
            "timestamp": "2026-04-28T12:00:00",
            "selected_skill": "playwright-skill",
            "skills_used": ["playwright-skill"],
            "intent": "implement_ui_confirmation_test",
            "reason": "regression",
            "decision": "HANDOFF",
            "model": "gpt-5.5",
        }

        row = render_recent_activity(event)

        self.assertIn("model-badge vendor-openai", row)
        self.assertIn("gpt-5.5", row)
        self.assertIn("recent-intent-cell", row)
        self.assertIn("implement_ui_confirmation_test", row)

    def test_model_extraction_supports_nested_legacy_shapes(self):
        self.assertEqual(
            extract_model_name({"model_info": {"name": "claude-sonnet-4.5"}}),
            "claude-sonnet-4.5",
        )
        self.assertEqual(extract_model_name({}), "Unknown model")

    def test_vendor_inference_covers_known_and_unknown_models(self):
        self.assertEqual(infer_model_vendor("gpt-5.5"), ("openai", "OA"))
        self.assertEqual(infer_model_vendor("claude-sonnet-4.5"), ("anthropic", "A"))
        self.assertEqual(infer_model_vendor("gemini-2.5-pro"), ("google", "G"))
        self.assertEqual(infer_model_vendor("custom-local"), ("unknown", "?"))

    def test_model_badge_escapes_model_name(self):
        badge = render_model_badge({"model": "gpt-5.5<script>"})

        self.assertIn("gpt-5.5&lt;script&gt;", badge)
        self.assertNotIn("gpt-5.5<script>", badge)

    def test_model_badge_uses_simple_icons_for_known_vendor(self):
        badge = render_model_badge({"model": "gpt-5.5"})

        self.assertIn("cdn.jsdelivr.net/npm/simple-icons@v15/icons/openai.svg", badge)
        self.assertIn('class="vendor-icon"', badge)

    def test_simple_icon_url_returns_empty_for_unknown_vendor(self):
        self.assertEqual(simple_icon_url("openai"), "https://cdn.jsdelivr.net/npm/simple-icons@v15/icons/openai.svg")
        self.assertEqual(simple_icon_url("unknown"), "")

    def test_all_link_renders_complete_skill_leaderboard(self):
        html = render_html(
            total_calls=3,
            most_used_name="analysis-skill",
            most_used_count=2,
            unique_skills=2,
            decision_summary={"H": 1, "S": 1, "N": 0},
            policy_summary={"lookups": 0, "H": 0, "M": 0, "E": 0},
            recent_events=[],
            skills_summary=[("analysis-skill", 2)],
            all_skills_summary=[("analysis-skill", 2), ("playwright-skill", 1)],
            consulted_at="2026-04-28T12:00:00Z",
            latest_event_at="2026-04-28T12:00:00Z",
            treemap_json="[]",
            all_events_json="[]",
            registry_json="{}",
            environment_info="demo / user",
            staleness_html="",
        )

        self.assertIn("All Skills", html)
        self.assertIn("analysis-skill", html)
        self.assertIn("playwright-skill", html)
        self.assertIn("<strong>2</strong>", html)
        self.assertIn("<strong>1</strong>", html)

    def test_model_count_row_renders_badge_and_count(self):
        row = render_model_count_row(1, "claude-sonnet-4-6", 7)

        self.assertIn('class="rank-index">1<', row)
        self.assertIn("model-badge vendor-anthropic", row)
        self.assertIn("claude-sonnet-4-6", row)
        self.assertIn("<strong>7</strong>", row)

    def test_render_html_includes_hits_per_model_card(self):
        html = render_html(
            total_calls=3,
            most_used_name="analysis-skill",
            most_used_count=2,
            unique_skills=1,
            decision_summary={"H": 1, "S": 0, "N": 0},
            policy_summary={"lookups": 0, "H": 0, "M": 0, "E": 0},
            recent_events=[],
            skills_summary=[("analysis-skill", 2)],
            all_skills_summary=[("analysis-skill", 2)],
            consulted_at="2026-04-28T12:00:00Z",
            latest_event_at="2026-04-28T12:00:00Z",
            treemap_json="[]",
            all_events_json="[]",
            registry_json="{}",
            environment_info="demo / user",
            staleness_html="",
            models_summary=[("claude-sonnet-4-6", 5), ("Unknown model", 2)],
        )

        self.assertIn("Hits per Model", html)
        self.assertIn("claude-sonnet-4-6", html)
        self.assertIn("Unknown model", html)
        self.assertIn("<strong>5</strong>", html)
        self.assertIn("<strong>2</strong>", html)


if __name__ == "__main__":
    unittest.main()
