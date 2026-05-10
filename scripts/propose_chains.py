#!/usr/bin/env python3
"""propose_chains.py -- Draft chain_definition.json files for chain-candidate skills.

Reads registry_health.json for skills flagged with missing_chain_definition,
calls the Anthropic API (using the calling agent's model from env vars),
and writes draft proposals to ~/.agents/dispatcher-data/chain_proposals/.

Run automatically after build_registry.py, or manually:
    python scripts/propose_chains.py [--skill <name>] [--dry-run]
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Model resolution — use the calling agent's model, never hardcode
# ---------------------------------------------------------------------------

def resolve_model() -> str:
    """Pick up the model from the calling agent's environment."""
    for env in (
        "SKILL_DISPATCH_MODEL", "AGENT_MODEL",
        "ANTHROPIC_MODEL", "CODEX_MODEL", "OPENAI_MODEL",
    ):
        val = os.environ.get(env, "").strip()
        if val:
            return val
    return "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
PERSISTENT_BASE = Path.home() / ".agents" / "dispatcher-data"
REGISTRY_DIR = PERSISTENT_BASE / "registry" if ".agents" in str(SKILL_ROOT).lower() else SKILL_ROOT / "registry"
PROPOSALS_DIR = PERSISTENT_BASE / "chain_proposals"
SKILLS_ROOT = Path.home() / ".agents" / "skills"


# ---------------------------------------------------------------------------
# Few-shot examples — loaded from the two completed chain definitions
# ---------------------------------------------------------------------------

def _load_examples() -> str:
    examples = []
    for skill_name in ("bug-fix-lifecycle", "new-feature-sdlc-skill"):
        p = SKILLS_ROOT / skill_name / "config" / "chain_definition.json"
        if p.exists():
            examples.append(f"### Example: {skill_name}\n```json\n{p.read_text(encoding='utf-8').strip()}\n```")
    return "\n\n".join(examples) if examples else "(no examples found)"


# ---------------------------------------------------------------------------
# Registry skill summary for the prompt (name + description + intents)
# ---------------------------------------------------------------------------

def _build_skill_summary(registry: dict) -> str:
    skills = registry.get("skills", [])
    if isinstance(skills, dict):
        skills = list(skills.values())
    lines = []
    for s in sorted(skills, key=lambda x: x.get("name", "")):
        name = s.get("name", "?")
        meta = s.get("metadata", {})
        desc = (meta.get("description") or s.get("description") or "")[:120]
        intents = ", ".join(meta.get("accepted_intents", [])[:4])
        lines.append(f"- {name}: {desc}" + (f" [intents: {intents}]" if intents else ""))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a chain definition generator for the Antigravity harness orchestrator.

Your job: given a skill's SKILL.md and the list of available sub-skills, generate a
chain_definition.json that maps the skill's documented workflow to concrete sub-skill invocations.

## Schema

```json
{
  "chain_name": "string — must match the skill name exactly",
  "description": "string — one sentence describing the full chain",
  "phases": [
    {
      "id": "string — snake_case unique identifier",
      "name": "string — human-readable phase name starting with Step N",
      "skill": "string | null — sub-skill name from the available list, or null for agent-handled steps",
      "intent": "string — telemetry intent tag",
      "reason": "string — why this phase exists; what it produces",
      "risk": "low | medium | high",
      "pass_context_forward": true,
      "query_suffix": "string — REQUIRED for self-gating phases; tells the sub-skill when to declare itself not applicable",
      "_note": "string — optional, only for null-skill phases"
    }
  ]
}
```

## Rules

1. `skill: null` means the executing agent does the work directly (e.g., writing code, writing a report).
2. Every non-null skill MUST exist in the available sub-skills list provided in the user message.
3. Phases that may not apply to all bug/feature types MUST include a `query_suffix` that instructs the sub-skill to self-declare: "state '[phase name]: not applicable for this case' and stop."
4. Use `pass_context_forward: true` only when the NEXT phase genuinely needs this phase's output as context.
5. Map phases directly to the skill's documented workflow — do not invent phases not described.
6. Security-related phases must have `risk: high` and a query_suffix warning against exploiting live systems.
7. The final phase is typically agent-handled (structured report), with a query_suffix specifying the required report sections.
8. Output ONLY the raw JSON — no markdown fences, no explanation, no preamble.

## Completed examples

{examples}
"""


# ---------------------------------------------------------------------------
# Core generation
# ---------------------------------------------------------------------------

def propose_one(skill_name: str, skill_md: str, skill_summary: str, model: str, dry_run: bool) -> dict | None:
    """Call the Anthropic API and return the parsed chain_definition dict, or None on failure."""
    if dry_run:
        print(f"  [dry-run] would call {model} for {skill_name}")
        return {"chain_name": skill_name, "description": "DRY RUN", "phases": []}

    try:
        import anthropic
    except ImportError:
        print("  [!] anthropic SDK not installed. Run: pip install anthropic", file=sys.stderr)
        return None

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("  [!] ANTHROPIC_API_KEY not set.", file=sys.stderr)
        return None

    examples = _load_examples()
    system = SYSTEM_PROMPT.replace("{examples}", examples)
    user_msg = (
        f"## Available sub-skills\n\n{skill_summary}\n\n"
        f"## Generate chain_definition.json for: {skill_name}\n\n"
        f"```\n{skill_md}\n```"
    )

    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text.strip()
        # Strip accidental markdown fences
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"  [!] Model returned invalid JSON for {skill_name}: {exc}", file=sys.stderr)
        return None
    except Exception as exc:
        print(f"  [!] API error for {skill_name}: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Propose chain_definition.json drafts for chain-candidate skills.")
    parser.add_argument("--skill", help="Propose for a single skill by name (skips health report lookup).")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without calling the API.")
    args = parser.parse_args()

    model = resolve_model()
    print(f"[*] propose_chains.py | model={model}")

    # Load registry for skill summary
    registry_path = REGISTRY_DIR / "SKILL_REGISTRY.json"
    if not registry_path.exists():
        print(f"[!] Registry not found at {registry_path}. Run build_registry.py first.", file=sys.stderr)
        return 1
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    skill_summary = _build_skill_summary(registry)

    # Determine candidates
    if args.skill:
        candidates = [args.skill]
    else:
        health_path = REGISTRY_DIR / "registry_health.json"
        if not health_path.exists():
            print(f"[!] Health report not found at {health_path}.", file=sys.stderr)
            return 1
        health = json.loads(health_path.read_text(encoding="utf-8"))
        candidates = [
            v["skill"] for v in health.get("issues", {}).values()
            if "missing_chain_definition" in v.get("issues", [])
        ]

    if not candidates:
        print("[*] No chain candidates found — nothing to propose.")
        return 0

    print(f"[*] Candidates: {candidates}")
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    proposed, failed = [], []

    for skill_name in candidates:
        print(f"\n  -> {skill_name}")
        skill_md_path = SKILLS_ROOT / skill_name / "SKILL.md"
        if not skill_md_path.exists():
            print(f"     [!] SKILL.md not found, skipping.")
            failed.append(skill_name)
            continue

        skill_md = skill_md_path.read_text(encoding="utf-8")
        chain_def = propose_one(skill_name, skill_md, skill_summary, model, args.dry_run)

        if chain_def is None:
            failed.append(skill_name)
            continue

        out_dir = PROPOSALS_DIR / skill_name
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "chain_definition.draft.json"
        out_path.write_text(json.dumps(chain_def, indent=2) + "\n", encoding="utf-8")

        # Write a human-readable review note alongside
        note_path = out_dir / "REVIEW.md"
        note_path.write_text(
            f"# Chain proposal: {skill_name}\n\n"
            f"Generated: {datetime.now().isoformat()}\n"
            f"Model: {model}\n\n"
            f"## Review checklist\n\n"
            f"- [ ] Every non-null skill exists in the registry\n"
            f"- [ ] Self-gating phases have appropriate query_suffix\n"
            f"- [ ] Agent-handled phases (skill: null) are the right choice\n"
            f"- [ ] pass_context_forward is set correctly\n"
            f"- [ ] Phase order matches the skill's documented workflow\n\n"
            f"## To approve\n\n"
            f"```\n"
            f"cp \"{out_path}\" \"{SKILLS_ROOT / skill_name / 'config' / 'chain_definition.json'}\"\n"
            f"```\n",
            encoding="utf-8",
        )
        print(f"     draft -> {out_path}")
        proposed.append(skill_name)

    print(f"\n[*] Done: {len(proposed)} proposed, {len(failed)} failed")
    if proposed:
        print(f"    Review drafts at: {PROPOSALS_DIR}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
