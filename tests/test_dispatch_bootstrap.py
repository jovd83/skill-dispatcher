import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "dispatch_bootstrap.py"


class DispatchBootstrapTests(unittest.TestCase):
    def test_bootstrap_generates_payload_and_cache_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            repo_root = temp_root / "demo-repo"
            repo_root.mkdir(parents=True)
            (repo_root / ".git").mkdir()

            project_memory_file = temp_root / "project_memory.json"
            shared_memory_file = temp_root / "shared_memory.json"
            cache_dir = temp_root / "cache"

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
                            "content": "Prefer the repo-local Angular workflow in this repository.",
                            "tags": ["routing"],
                        }
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
                    "--cache-dir",
                    str(cache_dir),
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
            self.assertEqual(payload["command"], "dispatch-bootstrap")
            self.assertEqual(payload["policy_lookup"]["status"], "hit")
            self.assertEqual(payload["policy_lookup"]["source"], "both")
            self.assertIn("project-memory -> shared-memory", payload["bootstrap_note"])
            self.assertIn("Prefer the repo-local Angular workflow in this repository.", payload["bootstrap_note"])
            self.assertTrue(Path(payload["cache_files"]["json"]).exists())
            self.assertTrue(Path(payload["cache_files"]["markdown"]).exists())


if __name__ == "__main__":
    unittest.main()
