import json
import os
import sys
import subprocess
from pathlib import Path

def get_shared_memory_path():
    # Try to find the shared-memory skill location from the registry if possible
    # But for a script in the same tree, we can guess or use an environment variable
    skill_dispatcher_dir = Path(__file__).parent.parent
    registry_path = skill_dispatcher_dir / "registry" / "SKILL_REGISTRY.json"
    
    if registry_path.exists():
        try:
            with open(registry_path, "r", encoding="utf-8") as f:
                registry = json.load(f)
                for skill in registry.get("skills", []):
                    if skill.get("name") == "shared-memory":
                        return Path(skill.get("location"))
        except Exception:
            pass
            
    # Fallback to sibling directory
    fallback = skill_dispatcher_dir.parent.parent / "shared-memory"
    if fallback.exists():
        return fallback
        
    return None

def check_policies(topic="RoutingPolicies"):
    shared_memory_dir = get_shared_memory_path()
    if not shared_memory_dir:
        print(f"[!] Warning: shared-memory skill not found in registry or siblings.")
        return None

    manage_script = shared_memory_dir / "scripts" / "manage_memory.py"
    if not manage_script.exists():
        print(f"[!] Warning: manage_memory.py not found at {manage_script}")
        return None

    try:
        # Check if topic exists first
        result = subprocess.run(
            [sys.executable, str(manage_script), "list-topics", "--format", "json"],
            capture_output=True,
            text=True,
            check=True
        )
        topics_info = json.loads(result.stdout)
        
        has_topic = any(t["topic"] == topic for t in topics_info.get("topics", []))
        if not has_topic:
            return None

        # Read the topic
        result = subprocess.run(
            [sys.executable, str(manage_script), "read", "--topic", topic, "--format", "json"],
            capture_output=True,
            text=True,
            check=True
        )
        return json.loads(result.stdout)
    except Exception as e:
        print(f"[!] Error querying shared memory: {e}")
        return None

def main():
    print("[*] Querying shared-memory for global routing policies...")
    policies = check_policies()
    if policies and policies.get("entries"):
        print(f"[*] Found {len(policies['entries'])} global policies:")
        for entry in policies["entries"]:
            print(f"  - [{entry['id']}] {entry['content']}")
        
        # Write a temporary advice file for the dispatcher to consume
        dispatcher_dir = Path(__file__).parent.parent
        advice_file = dispatcher_dir / "registry" / "SHARED_ADVICE.json"
        with open(advice_file, "w", encoding="utf-8") as f:
            json.dump(policies, f, indent=2)
        print(f"[*] Shared advice cached for dispatcher: {advice_file}")
    else:
        print("[*] No global routing policies found in shared-memory.")

if __name__ == "__main__":
    main()
