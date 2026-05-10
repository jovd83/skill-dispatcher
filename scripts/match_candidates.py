#!/usr/bin/env python3
"""match_candidates.py - Score skills against a routing intent using registry metadata.

The agent owns the final routing decision. This script provides a deterministic,
metadata-grounded shortlist that anchors that decision in real `dispatcher-*` fields
rather than free-form scanning of all 78 skills.

Scoring (per candidate, before hard gates):
    +5 per exact accepted_intents match
    +3 per capability keyword match
    +2 per stack_tags overlap
    +2 if input_artifacts contains --input-artifact
    +2 if output_artifacts contains --target-artifact
    +1 if layer aligns with intent verb (audit/review -> feedback, build/create -> execution)
    +0.5 per description keyword match (last-resort fallback)

Hard gates (skill is excluded with reason):
    lifecycle == "archived"
    risk > --max-risk
    name == "skill-dispatcher" (the dispatcher never routes to itself)

Usage:
    match_candidates.py --intent audit_skill_frontmatter
    match_candidates.py --intent design_ui --keywords angular,component --stack angular --max-risk medium
    match_candidates.py --intent review_code --top-n 3 --format text
"""

import argparse
import json
import os
import sys
from pathlib import Path


RISK_RANK = {"low": 0, "medium": 1, "high": 2}

# Intent verbs that signal layer preference
FEEDBACK_VERBS = {"audit", "review", "verify", "check", "assess", "evaluate", "score", "validate"}
EXECUTION_VERBS = {"build", "create", "generate", "implement", "design", "scaffold", "refactor", "deploy", "run"}
INFORMATION_VERBS = {"read", "load", "discover", "find", "extract", "summarize", "fetch", "analyze"}


def _resolve_registry_path() -> Path | None:
    """Find the live SKILL_REGISTRY.json from common install locations."""
    candidates = [
        Path.home() / ".agents" / "dispatcher-data" / "registry" / "SKILL_REGISTRY.json",
        Path(__file__).parent.parent / "registry" / "SKILL_REGISTRY.json",
    ]
    env_override = os.environ.get("SKILL_DISPATCH_REGISTRY")
    if env_override:
        candidates.insert(0, Path(env_override))
    return next((p for p in candidates if p.exists()), None)


def _normalize_skills(payload: dict) -> dict:
    """Return skills as a {name: {...metadata...}} dict regardless of registry shape."""
    raw = payload.get("skills", {})
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        return {item["name"]: item for item in raw if isinstance(item, dict) and "name" in item}
    return {}


def _intent_layer_preference(intent: str) -> str:
    """Guess which layer the intent prefers based on its leading verb."""
    if not intent:
        return ""
    verb = intent.split("_", 1)[0].lower()
    if verb in FEEDBACK_VERBS:
        return "feedback"
    if verb in EXECUTION_VERBS:
        return "execution"
    if verb in INFORMATION_VERBS:
        return "information"
    return ""


def _intent_keywords(intent: str) -> set[str]:
    """Split an intent like 'audit_skill_frontmatter' into matchable keywords."""
    if not intent:
        return set()
    return {part for part in intent.lower().replace("-", "_").split("_") if part}


def score_skill(skill: dict, intent: str, keywords: list[str], stack: list[str],
                input_artifact: str, target_artifact: str) -> dict:
    """Return a per-skill score breakdown. Higher is better."""
    breakdown: dict[str, list | float] = {
        "accepted_intents": [],
        "capabilities": [],
        "stack_tags": [],
        "input_artifacts": [],
        "output_artifacts": [],
        "layer_alignment": 0.0,
        "description_match": [],
    }
    score = 0.0

    intent_norm = (intent or "").strip().lower()
    intent_kw = _intent_keywords(intent_norm)
    user_kw = {k.strip().lower() for k in keywords if k.strip()}
    all_kw = intent_kw | user_kw
    stack_lower = {s.strip().lower() for s in stack if s.strip()}

    # Exact accepted_intents match (strongest signal)
    accepted = [a.lower() for a in skill.get("accepted_intents", [])]
    if intent_norm and intent_norm in accepted:
        breakdown["accepted_intents"].append(intent_norm)
        score += 5
    # Partial accepted_intents match (intent keyword appears in any accepted_intent)
    for kw in intent_kw:
        for a in accepted:
            if kw in a and a not in breakdown["accepted_intents"]:
                breakdown["accepted_intents"].append(a)
                score += 1
                break

    # Capability keyword match
    capabilities = [c.lower() for c in skill.get("capabilities", [])]
    for cap in capabilities:
        cap_words = set(cap.replace("-", " ").split())
        if cap_words & all_kw:
            breakdown["capabilities"].append(cap)
            score += 3

    # Stack tags overlap
    stack_tags = [s.lower() for s in skill.get("stack_tags", [])]
    for tag in stack_tags:
        if tag in stack_lower or tag in all_kw:
            breakdown["stack_tags"].append(tag)
            score += 2

    # Input artifact compatibility
    if input_artifact:
        ia = input_artifact.strip().lower()
        skill_ia = [a.lower() for a in skill.get("input_artifacts", [])]
        if ia in skill_ia:
            breakdown["input_artifacts"].append(ia)
            score += 2

    # Output artifact compatibility (must produce what the next step needs)
    if target_artifact:
        ta = target_artifact.strip().lower()
        skill_oa = [a.lower() for a in skill.get("output_artifacts", [])]
        if ta in skill_oa:
            breakdown["output_artifacts"].append(ta)
            score += 2

    # Layer alignment (cheap signal, low weight)
    preferred_layer = _intent_layer_preference(intent_norm)
    if preferred_layer and skill.get("layer") == preferred_layer:
        breakdown["layer_alignment"] = 1
        score += 1

    # Description keyword match (last-resort, half-weight)
    raw_desc = skill.get("description") or ""
    if isinstance(raw_desc, list):
        raw_desc = " ".join(str(x) for x in raw_desc)
    desc = str(raw_desc).lower()
    if desc:
        matched_words = [kw for kw in all_kw if kw and len(kw) > 3 and kw in desc]
        if matched_words:
            breakdown["description_match"] = matched_words[:3]  # cap to avoid spam
            score += 0.5 * min(len(matched_words), 4)

    return {"score": round(score, 1), "breakdown": breakdown}


def filter_candidates(skills: dict, max_risk: str) -> tuple[dict, list]:
    """Apply hard gates. Returns (kept, filtered_out_with_reasons)."""
    max_rank = RISK_RANK.get(max_risk.lower(), RISK_RANK["high"]) if max_risk else RISK_RANK["high"]
    kept = {}
    filtered = []
    for name, skill in skills.items():
        if name == "skill-dispatcher":
            filtered.append({"skill": name, "reason": "dispatcher does not route to itself"})
            continue
        if skill.get("lifecycle") == "archived":
            filtered.append({"skill": name, "reason": "lifecycle: archived"})
            continue
        skill_risk = (skill.get("risk") or "low").lower()
        if RISK_RANK.get(skill_risk, RISK_RANK["high"]) > max_rank:
            filtered.append({"skill": name, "reason": f"risk {skill_risk} > max-risk {max_risk}"})
            continue
        kept[name] = skill
    return kept, filtered


def render_text(result: dict) -> str:
    """Render a human-readable summary of the candidate shortlist."""
    lines = [
        f"Intent       : {result['intent']}",
        f"Layer hint   : {result.get('preferred_layer', '-') or '-'}",
        f"Considered   : {result['total_considered']} skills",
        f"After gates  : {result['after_gates']} kept, {len(result['filtered_out'])} filtered",
        "",
        "Top candidates:",
    ]
    for i, c in enumerate(result["candidates"], start=1):
        lines.append(f"  {i}. {c['skill']:<40} score={c['score']}")
        b = c["breakdown"]
        bits = []
        if b.get("accepted_intents"):
            bits.append(f"intents={b['accepted_intents']}")
        if b.get("capabilities"):
            bits.append(f"caps={b['capabilities']}")
        if b.get("stack_tags"):
            bits.append(f"stack={b['stack_tags']}")
        if b.get("layer_alignment"):
            bits.append("layer-aligned")
        if bits:
            lines.append(f"      {' | '.join(bits)}")
    if result["candidates"]:
        lines.append("")
        lines.append("Pick from the shortlist; override only with a contextual reason worth logging.")
    else:
        lines.append("")
        lines.append("No candidates scored > 0. Either widen the intent or check the registry.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Score skills against a routing intent using registry metadata.",
    )
    parser.add_argument("--intent", required=True, help="Normalized routing intent (e.g. 'audit_skill_frontmatter').")
    parser.add_argument("--keywords", default="", help="Comma-separated free-text keywords from the user query.")
    parser.add_argument("--stack", default="", help="Comma-separated repo-native stack tags (e.g. 'angular,vitest').")
    parser.add_argument("--input-artifact", default="", help="Artifact the agent currently has.")
    parser.add_argument("--target-artifact", default="", help="Artifact expected from the next skill.")
    parser.add_argument("--max-risk", default="high", choices=["low", "medium", "high"], help="Risk ceiling.")
    parser.add_argument("--top-n", type=int, default=5, help="How many candidates to return.")
    parser.add_argument("--format", default="json", choices=["json", "text"], help="Output format.")
    parser.add_argument("--registry", default="", help="Override path to SKILL_REGISTRY.json.")
    parser.add_argument("--include-zero-score", action="store_true", help="Return zero-scored candidates too.")
    args = parser.parse_args()

    registry_path = Path(args.registry) if args.registry else _resolve_registry_path()
    if registry_path is None or not registry_path.exists():
        print("[!] SKILL_REGISTRY.json not found. Set SKILL_DISPATCH_REGISTRY or run build_registry.py first.", file=sys.stderr)
        return 1

    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    skills = _normalize_skills(payload)
    total = len(skills)

    kept, filtered = filter_candidates(skills, args.max_risk)
    keywords = [k for k in args.keywords.split(",") if k]
    stack = [s for s in args.stack.split(",") if s]

    scored = []
    for name, skill in kept.items():
        result = score_skill(skill, args.intent, keywords, stack, args.input_artifact, args.target_artifact)
        if result["score"] > 0 or args.include_zero_score:
            scored.append({
                "skill": name,
                "score": result["score"],
                "layer": skill.get("layer", "?"),
                "risk": skill.get("risk", "?"),
                "breakdown": result["breakdown"],
            })

    scored.sort(key=lambda c: c["score"], reverse=True)
    candidates = scored[:args.top_n]

    output = {
        "intent": args.intent,
        "preferred_layer": _intent_layer_preference(args.intent),
        "registry_path": str(registry_path),
        "total_considered": total,
        "after_gates": len(kept),
        "filtered_out": filtered[:10],  # cap output size
        "candidates": candidates,
    }

    if args.format == "json":
        print(json.dumps(output, indent=2))
    else:
        print(render_text(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
