"""Mirror one dispatch event into Honcho memory (optional).

dispatch_logger.py calls this only when SKILL_DISPATCH_HONCHO_SYNC=1. It is off by default since 4.0.0:
with the hooks logging every skill use, mirroring each event (and scheduling a Honcho dream after it)
filled the user representation with dispatch noise.

Environment: HONCHO_API_KEY (else the key in Antigravity's mcp_config.json), HONCHO_WORKSPACE_ID,
HONCHO_PEER_ID.
"""
import sys
import os
import json
import requests
from pathlib import Path

def get_api_key():
    # 1. Check environment variable
    api_key = os.environ.get("HONCHO_API_KEY")
    if api_key:
        return api_key

    # 2. Check mcp_config.json
    try:
        config_path = Path.home() / ".gemini" / "antigravity" / "mcp_config.json"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                key = config.get("mcpServers", {}).get("honcho", {}).get("headers", {}).get("x-api-key")
                if key and key != "REPLACE_WITH_YOUR_HONCHO_API_KEY":
                    return key
    except Exception:
        pass
    return None

def main():
    if len(sys.argv) < 2:
        print("Usage: sync_to_honcho.py <entry_json_string>")
        sys.exit(1)
        
    entry_str = sys.argv[1]
    try:
        entry = json.loads(entry_str)
    except Exception as e:
        print(f"Error parsing entry JSON: {e}")
        sys.exit(1)
        
    api_key = get_api_key()
    if not api_key:
        print("Honcho API key not found. Skipping sync.")
        sys.exit(0)
        
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    base_url = "https://api.honcho.dev/v3"
    workspace_id = os.environ.get("HONCHO_WORKSPACE_ID", "the_sublime")
    peer_id = os.environ.get("HONCHO_PEER_ID", "jochim")
    
    # 1. Determine session ID based on chain_id
    chain_id = entry.get("chain_id", "").strip()
    session_id = f"chain-{chain_id}" if chain_id else f"dispatch-{entry.get('selected_skill', 'general')}"
    
    # Clean session_id to conform to pattern ^[a-zA-Z0-9_-]+$
    session_id = "".join([c for c in session_id if c.isalnum() or c in ("-", "_")])
    
    # Helper to check workspace and create if missing
    def ensure_workspace():
        r = requests.post(f"{base_url}/workspaces", headers=headers, json={"id": workspace_id})
        if r.status_code in (200, 201):
            print(f"Workspace '{workspace_id}' verified/created.")
            # Also verify peer
            requests.post(f"{base_url}/workspaces/{workspace_id}/peers", headers=headers, json={"id": peer_id})
            return True
        return r.status_code in (200, 201, 409)

    # 2. Try to create the session
    print(f"Syncing dispatch to Honcho session '{session_id}'...")
    try:
        r = requests.post(f"{base_url}/workspaces/{workspace_id}/sessions", headers=headers, json={"id": session_id})
        if r.status_code == 404:
            # Workspace missing, create it and retry
            if ensure_workspace():
                r = requests.post(f"{base_url}/workspaces/{workspace_id}/sessions", headers=headers, json={"id": session_id})
        
        # 3. Create the message
        # Format the dispatch event details as the content
        content = (
            f"Skill Dispatch: '{entry.get('selected_skill')}'\n"
            f"Intent: {entry.get('intent')}\n"
            f"Reason: {entry.get('reason')}\n"
            f"Decision: {entry.get('decision')}\n"
            f"Chain ID: {chain_id}\n"
        )
        if entry.get("target"):
            content += f"Target: {entry.get('target')}\n"
        if entry.get("model"):
            content += f"Model: {entry.get('model')}\n"
        if entry.get("phase_status"):
            content += f"Phase Status: {entry.get('phase_status')}\n"
            
        msg_payload = {
            "messages": [
                {
                    "peer_id": peer_id,
                    "content": content,
                    "metadata": {
                        "source": "skill-dispatcher-telemetry",
                        "skills_used": entry.get("skills_used", []),
                        "matched_fields": entry.get("matched_fields", []),
                        "match_score": entry.get("match_score"),
                        "policy_lookup": entry.get("policy_lookup")
                    }
                }
            ]
        }
        
        r_msg = requests.post(
            f"{base_url}/workspaces/{workspace_id}/sessions/{session_id}/messages",
            headers=headers,
            json=msg_payload
        )
        print(f"Message post status: {r_msg.status_code}")
        
        # 4. Schedule a dream/reasoning update to keep Jochim's profile perfectly synchronized
        if r_msg.status_code in (200, 201):
            requests.post(f"{base_url}/workspaces/{workspace_id}/schedule_dream", headers=headers, json={})
            print("Honcho dream scheduled.")
            
    except Exception as e:
        print(f"Error syncing to Honcho: {e}")

if __name__ == "__main__":
    main()
