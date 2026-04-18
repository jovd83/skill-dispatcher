import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "prepare_dispatch_context.py"


class PrepareDispatchContextTests(unittest.TestCase):
    def test_project_memory_wins_over_shared_defaults_and_stale_shared_entries_are_filtered(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            repo_root = temp_root / "demo-repo"
            repo_root.mkdir(parents=True)
            (repo_root / ".git").mkdir()

            project_memory_file = temp_root / "project_memory.json"
            shared_memory_file = temp_root / "shared_memory.json"

            project_store = {
                "schema_version": "1.0",
                "repo_root": str(repo_root),
                "topics": {
                    "RoutingPolicies": [
                        {
                            "id": 1,
                            "status": "active",
                            "created_at": "2026-04-10T00:00:00Z",
                            "source": "UnitTest",
                            "confidence": 1.0,
                            "content": "Load codebase-context before high-risk repo work.",
                            "tags": ["routing"],
                        },
                        {
                            "id": 2,
                            "status": "active",
                            "created_at": "2026-04-12T00:00:00Z",
                            "source": "UnitTest",
                            "confidence": 1.0,
                            "content": "Prefer the repo-native Playwright suite over global UI defaults in this repository.",
                            "tags": ["routing"],
                        },
                    ]
                },
            }
            shared_store = {
                "schema_version": "2.0",
                "topics": {
                    "RoutingPolicies": [
                        {
                            "id": 1,
                            "status": "active",
                            "created_at": "2026-04-01T00:00:00Z",
                            "last_reviewed_at": "2026-04-01T00:00:00Z",
                            "review_after_days": 365,
                            "source": "UnitTest",
                            "confidence": 0.95,
                            "content": "Load codebase-context before high-risk repo work.",
                            "tags": ["routing"],
                        },
                        {
                            "id": 2,
                            "status": "active",
                            "created_at": "2026-04-05T00:00:00Z",
                            "last_reviewed_at": "2026-04-05T00:00:00Z",
                            "review_after_days": 365,
                            "source": "UnitTest",
                            "confidence": 0.93,
                            "content": "For external API work, load get-api-docs before implementation.",
                            "tags": ["routing"],
                        },
                        {
                            "id": 3,
                            "status": "active",
                            "created_at": "2024-01-01T00:00:00Z",
                            "last_reviewed_at": "2024-01-01T00:00:00Z",
                            "review_after_days": 30,
                            "source": "UnitTest",
                            "confidence": 0.97,
                            "content": "Stale shared routing policy that should be filtered out.",
                            "tags": ["routing"],
                        },
                    ]
                },
            }

            project_memory_file.write_text(json.dumps(project_store), encoding="utf-8")
            shared_memory_file.write_text(json.dumps(shared_store), encoding="utf-8")

            env = os.environ.copy()
            env["AGENT_SHARED_MEMORY_PATH"] = str(shared_memory_file)

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--repo-root",
                    str(repo_root),
                    "--project-memory-file",
                    str(project_memory_file),
                    "--shared-min-confidence",
                    "0.8",
                    "--shared-max-age-days",
                    "365",
                    "--skip-cache",
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            resolved = payload["resolved_policies"]

            self.assertEqual(payload["policy_lookup"]["status"], "hit")
            self.assertEqual(payload["policy_lookup"]["source"], "both")
            self.assertEqual(payload["policy_lookup"]["hit_count"], 3)
            self.assertEqual(len(resolved), 3)
            self.assertEqual(
                [entry["policy_source"] for entry in resolved],
                ["project-memory", "project-memory", "shared-memory"],
            )
            self.assertEqual(
                resolved[0]["content"],
                "Load codebase-context before high-risk repo work.",
            )
            self.assertEqual(
                resolved[1]["content"],
                "Prefer the repo-native Playwright suite over global UI defaults in this repository.",
            )
            self.assertEqual(
                resolved[2]["content"],
                "For external API work, load get-api-docs before implementation.",
            )
            self.assertNotIn(
                "Stale shared routing policy that should be filtered out.",
                [entry["content"] for entry in resolved],
            )


if __name__ == "__main__":
    unittest.main()
