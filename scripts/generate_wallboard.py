#!/usr/bin/env python3
"""Skill Dispatch Wallboard - Generates a premium HTML/CSS dashboard for skill usage."""

import html
import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def format_timestamp_for_html(value) -> str:
    """Render filesystem timestamps in the same UTC format as wallboard metadata."""
    return datetime.fromtimestamp(value, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def extract_logged_skills(event):
    """Return every skill represented by a log event."""
    skills_used = event.get("skills_used")
    if isinstance(skills_used, list):
        normalized = [skill.strip() for skill in skills_used if isinstance(skill, str) and skill.strip()]
        if normalized:
            return normalized

    selected_skill = event.get("selected_skill", "Unknown")
    if isinstance(selected_skill, str) and selected_skill.strip():
        normalized = selected_skill.replace("+", ",").replace("&", ",")
        return [part.strip() for part in normalized.split(",") if part.strip()]

    return ["Unknown"]


def display_skill_label(event):
    """Render a readable label for recent activity."""
    skills = extract_logged_skills(event)
    if not skills:
        return event.get("selected_skill", "Unknown")

    if len(skills) > 1 and skills[0] == "skill-dispatcher":
        # Show the real skill as primary, and the dispatcher as secondary/context
        real_skill = skills[1]
        others = skills[2:]
        label = real_skill
        if others:
            label += f" <small style='opacity:0.6'>(+{len(others)})</small>"
        return label

    return " -> ".join(skills)


def detail_skill_name(event):
    """Return the primary skill used for detail drill-down from timeline rows."""
    skills = extract_logged_skills(event)
    if len(skills) > 1 and skills[0] == "skill-dispatcher":
        return skills[1]
    if skills:
        return skills[0]
    return event.get("selected_skill", "Unknown")


def render_skill_link(skill_name):
    """Render a clickable skill label that opens the detail page."""
    safe_label = html.escape(skill_name)
    safe_js_arg = html.escape(json.dumps(skill_name), quote=True)
    return f'<span class="clickable skill-link" onclick="showDetail({safe_js_arg})">{safe_label}</span>'


def render_skill_count_row(rank, skill_name, count, failure_stats=None):
    """Render a leaderboard row for a skill, its hit count, and optional failure rate.

    failure_stats: dict mapping skill_name -> (failures, completions). When provided
    and the skill has at least one phase_status event, a failure-rate badge is shown.
    """
    rate_html = ""
    if failure_stats and skill_name in failure_stats:
        fails, total = failure_stats[skill_name]
        if total > 0:
            pct = (fails / total) * 100
            tone = "tone-muted" if fails == 0 else ("tone-gold" if pct < 25 else "tone-red")
            rate_html = (
                f' <span class="failure-rate {tone}" '
                f'title="{fails} of {total} phase-completions failed">'
                f'{pct:.0f}% fail</span>'
            )
    return (
        '<div class="rank-row all-skill-row">'
        f'<span class="rank-index">{rank}</span>'
        f'<span class="all-skill-name">{render_skill_link(skill_name)}{rate_html}</span>'
        f'<strong>{count}</strong>'
        '</div>'
    )


def render_model_count_row(rank, model_name, count):
    """Render a leaderboard-style row for a model and its total hit count."""
    badge = render_model_badge({"model": model_name})
    return (
        '<div class="rank-row all-skill-row">'
        f'<span class="rank-index">{rank}</span>'
        f'<span class="all-skill-name">{badge}</span>'
        f'<strong>{count}</strong>'
        '</div>'
    )


def render_secondary_skill_links(event):
    """Render every non-primary skill in the event as separate detail links."""
    secondary_skills = event.get("_secondary_hit_skills")
    if not isinstance(secondary_skills, list):
        secondary_skills = extract_logged_skills(event)[1:]
    if not secondary_skills:
        return '<span class="muted-cell">none</span>'
    return " | ".join(render_skill_link(skill) for skill in secondary_skills)


def render_policy_summary(event):
    """Render a concise policy lookup summary."""
    policy = event.get("policy_lookup")
    if not isinstance(policy, dict):
        return '<span class="muted-cell">none</span>'

    status = str(policy.get("status", "miss")).strip().lower()
    source = str(policy.get("source", "none")).strip().lower()
    hit_count = int(policy.get("hit_count", 0) or 0)
    topic = html.escape(str(policy.get("topic", "RoutingPolicies")), quote=True)

    if status == "error":
        label = "policy error"
    elif status == "miss":
        label = "policy miss"
    elif status == "hit":
        source_label = {
            "shared-memory": "shared hit",
            "project-memory": "project hit",
            "both": "policy hit",
        }.get(source, "policy hit")
        label = f"{source_label} ({hit_count})" if hit_count else source_label
    else:
        label = html.escape(status)

    if policy.get("changed_routing"):
        label += " | changed routing"

    return f'<span class="policy-pill" title="{topic}">{html.escape(label)}</span>'


def extract_model_name(event):
    """Return the logged model name across current and legacy telemetry shapes."""
    for key in ("model", "model_name", "llm_model", "agent_model"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    for key in ("model", "model_info", "llm"):
        value = event.get(key)
        if isinstance(value, dict):
            nested = value.get("name") or value.get("model") or value.get("id")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()

    return "Unknown model"


def infer_model_vendor(model_name):
    """Infer model vendor from common model name prefixes."""
    normalized = model_name.strip().lower()
    if normalized in {"", "unknown model"}:
        return ("unknown", "?")
    if normalized.startswith(("gpt-", "o1", "o3", "o4", "o5")) or "codex" in normalized:
        return ("openai", "OA")
    if normalized.startswith("claude") or "anthropic" in normalized:
        return ("anthropic", "A")
    if normalized.startswith("gemini") or "google" in normalized:
        return ("google", "G")
    if normalized.startswith(("llama", "meta")):
        return ("meta", "M")
    if normalized.startswith("mistral") or normalized.startswith("mixtral"):
        return ("mistral", "Mi")
    if normalized.startswith("grok") or "xai" in normalized:
        return ("xai", "xAI")
    if normalized.startswith("deepseek"):
        return ("deepseek", "DS")
    if normalized.startswith("command") or "cohere" in normalized:
        return ("cohere", "Co")
    return ("unknown", "?")


SIMPLE_ICON_SLUGS = {
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "googlegemini",
    "meta": "meta",
    "mistral": "mistralai",
    "xai": "x",
    "deepseek": "deepseek",
    "cohere": "cohere",
}


def simple_icon_url(vendor):
    """Return the Simple Icons CDN URL for a known vendor."""
    slug = SIMPLE_ICON_SLUGS.get(vendor)
    if not slug:
        return ""
    return f"https://cdn.jsdelivr.net/npm/simple-icons@v15/icons/{slug}.svg"


def render_model_badge(event):
    """Render model vendor mark and name for activity tables."""
    model_name = extract_model_name(event)
    vendor, logo = infer_model_vendor(model_name)
    safe_model = html.escape(model_name)
    safe_vendor = html.escape(vendor)
    safe_logo = html.escape(logo)
    icon_url = html.escape(simple_icon_url(vendor), quote=True)
    title = html.escape(f"{vendor.title()} model: {model_name}", quote=True)
    icon_markup = (
        f'<img class="vendor-icon" src="{icon_url}" alt="{safe_vendor}" '
        'onerror="this.style.display=\'none\'; this.nextElementSibling.style.display=\'inline\';">'
        if icon_url
        else ""
    )
    return (
        f'<span class="model-badge vendor-{safe_vendor}" title="{title}">'
        f'<span class="vendor-logo">{icon_markup}<span class="vendor-fallback">{safe_logo}</span></span>'
        f'<span class="model-name">{safe_model}</span>'
        '</span>'
    )


def render_recent_activity(event):
    """Render a single recent activity row."""
    timestamp = event["timestamp"]
    date_part, time_part = timestamp.split("T", 1)
    time_label = time_part.split(".")[0]
    primary_skill = event.get("_hit_skill") or detail_skill_name(event)
    reason = html.escape(event.get("reason", ""), quote=True)
    intent = html.escape(event["intent"])
    decision = event.get("decision", "HANDOFF")
    decision_class = decision.lower()
    decision_label = html.escape(decision)

    return (
        '<tr>'
        f'<td class="recent-time-cell"><div>{date_part}</div><small>{time_label}</small></td>'
        f'<td><span class="badge {decision_class}" title="{decision_label}">{decision[0]}</span></td>'
        f'<td>{render_model_badge(event)}</td>'
        f'<td>{render_skill_link(primary_skill)}</td>'
        f'<td class="secondary-skills-cell">{render_secondary_skill_links(event)}</td>'
        f'<td class="recent-intent-cell" title="{reason}">{intent}</td>'
        f'<td class="policy-cell">{render_policy_summary(event)}</td>'
        '</tr>'
    )


def token_cost_report_roots(script_dir):
    """
    Resolve the ordered list of candidate roots that may contain token cost
    reports.

    Override via the `TOKEN_COST_REPORTS_DIR` environment variable
    (use `os.pathsep` to pass several paths). When the env var is set,
    only those paths are used. Otherwise, well-known defaults are tried in
    order. Non-existent paths are filtered out by `collect_token_cost_reports`.
    """
    override = os.environ.get("TOKEN_COST_REPORTS_DIR", "").strip()
    if override:
        return [Path(p).expanduser() for p in override.split(os.pathsep) if p.strip()]

    home = Path.home()
    return [
        # Sibling skill in this repo (current default)
        script_dir.parent / "token_count_skill" / "repository-reports",
        # token-usage-cost-report skill installed for the user
        home / ".claude" / "skills" / "token-usage-cost-report" / "repository-reports",
        home / ".agents" / "skills" / "token-usage-cost-report" / "repository-reports",
        # Sibling skill installs that match the canonical name
        script_dir.parent / "token-usage-cost-report" / "repository-reports",
    ]


def collect_token_cost_reports(script_dir):
    """
    Discover token cost reports produced by the token-usage-cost-report skill.
    Walks each candidate root from `token_cost_report_roots()` and reads
    `<root>/<repo>/report.data.json` for `summary.cost_total_usd`.
    Dedupes by repo name (first matching root wins).

    Returns (items, roots_searched) where:
      - items: list of {name, cost_usd, href, source_root} sorted by cost desc
      - roots_searched: list of {path, exists} for diagnostics
    """
    roots = token_cost_report_roots(script_dir)
    roots_searched = [{"path": str(r), "exists": r.exists()} for r in roots]

    items = []
    seen_names = set()
    for root in roots:
        if not root.exists():
            continue
        for entry in sorted(root.iterdir()):
            if not entry.is_dir() or entry.name in seen_names:
                continue
            data_file = entry / "report.data.json"
            html_file = entry / "report.html"
            if not data_file.exists():
                continue
            try:
                with open(data_file, "r", encoding="utf-8") as f:
                    payload = json.load(f)
            except Exception:
                continue
            cost = payload.get("summary", {}).get("cost_total_usd")
            if cost is None:
                continue
            try:
                cost_float = float(cost)
            except (TypeError, ValueError):
                continue
            seen_names.add(entry.name)
            items.append({
                "name": entry.name,
                "cost_usd": cost_float,
                "href": html_file.resolve().as_uri() if html_file.exists() else None,
                "source_root": str(root),
            })
    items.sort(key=lambda x: x["cost_usd"], reverse=True)
    return items, roots_searched


def render_token_cost_table(items, roots_searched=None):
    """Render the token cost reports list as a card-styled table."""
    roots_searched = roots_searched or []
    active_sources = {item["source_root"] for item in items}
    show_source_col = len(active_sources) > 1

    if not items:
        roots_html = "".join(
            f'<li><code>{html.escape(r["path"])}</code>'
            f' <span class="tone-muted">({"exists, no reports" if r["exists"] else "missing"})</span></li>'
            for r in roots_searched
        )
        env_hint = (
            '<p style="margin-top:16px"><strong>Tip:</strong> set '
            '<code>TOKEN_COST_REPORTS_DIR</code> '
            '(use <code>;</code> on Windows or <code>:</code> on POSIX to pass several paths) '
            'to point at a custom location.</p>'
        )
        return (
            '<div class="card" style="max-width: 900px; margin: 0 auto; padding: 32px;">'
            '<i>No token cost reports found.</i>'
            f'<p style="margin-top:16px">Roots searched:</p><ul>{roots_html}</ul>'
            f'{env_hint}'
            '</div>'
        )
    rows = []
    total = 0.0
    for item in items:
        name = html.escape(item["name"])
        cost_label = f'${item["cost_usd"]:.4f}'
        if item["href"]:
            href = html.escape(item["href"], quote=True)
            action = (
                f'<a href="{href}" class="btn btn-secondary" '
                f'target="_blank" rel="noopener noreferrer">Open Report</a>'
            )
        else:
            action = '<span class="tone-muted">No HTML</span>'
        source_cell = ""
        if show_source_col:
            source_cell = (
                f'<td class="tone-muted" style="font-size:0.82rem">'
                f'<code>{html.escape(item.get("source_root", ""))}</code></td>'
            )
        rows.append(
            '<tr>'
            f'<td>{name}</td>'
            f'<td style="text-align:right;font-variant-numeric:tabular-nums">{cost_label}</td>'
            f'{source_cell}'
            f'<td style="text-align:right">{action}</td>'
            '</tr>'
        )
        total += item["cost_usd"]

    source_header = '<th>Source</th>' if show_source_col else ''
    source_footer = '<td></td>' if show_source_col else ''
    return (
        '<div class="table-container" style="max-width: 1100px; margin: 0 auto;">'
        '<table>'
        '<thead><tr>'
        '<th>Repository</th>'
        '<th style="text-align:right">Total Cost (USD)</th>'
        f'{source_header}'
        '<th style="text-align:right">Action</th>'
        '</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        '<tfoot><tr>'
        f'<td><strong>Total ({len(items)} reports)</strong></td>'
        f'<td style="text-align:right;font-variant-numeric:tabular-nums"><strong>${total:.4f}</strong></td>'
        f'{source_footer}'
        '<td></td>'
        '</tr></tfoot>'
        '</table>'
        '</div>'
    )


def _parse_iso(timestamp: str):
    """Parse an event timestamp; return None on failure."""
    if not isinstance(timestamp, str) or not timestamp:
        return None
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


import re as _re


def _resolve_chain_skill(ev):
    """Resolve the real target skill from an event, handling skill-dispatcher as a wrapper."""
    skills = extract_logged_skills(ev)
    if len(skills) > 1 and skills[0] == "skill-dispatcher":
        return skills[1]
    return skills[0] if skills else "unknown"


def _build_chain_summary(chain_skill, chain_id, all_events, first_dt, chain_defs):
    """Build a chain summary dict from a list of events sharing a logical chain."""
    if not all_events:
        return None
    all_events = sorted(all_events, key=lambda e: e.get("timestamp", ""))
    first_ts = all_events[0].get("timestamp", "")
    last_ts  = all_events[-1].get("timestamp", first_ts)
    last_dt  = _parse_iso(last_ts)
    duration_sec = (last_dt - first_dt).total_seconds() if (last_dt and first_dt) else 0.0

    is_sequence_intent = any(e.get("decision") == "SEQUENCE" for e in all_events)

    seen_skills = {}
    ordered = []
    for ev in all_events:
        if ev.get("decision") == "SEQUENCE" and "chain_initiated" in ev.get("reason", ""):
            continue

        is_seq = ev.get("decision") == "SEQUENCE"
        # If it's a sequence, we treat all listed skills as planned/hit phases
        if is_seq:
            skills_to_process = [s for s in extract_logged_skills(ev) if s != "skill-dispatcher"]
        else:
            skills_to_process = [_resolve_chain_skill(ev)]

        status = ev.get("phase_status", "")
        ev_dt  = _parse_iso(ev.get("timestamp", ""))
        dt     = (ev_dt - first_dt).total_seconds() if (ev_dt and first_dt) else 0.0

        for skill in skills_to_process:
            if skill == "unknown":
                continue
            entry = {"ts": ev.get("timestamp", ""), "decision": ev.get("decision", "HANDOFF"),
                     "skill": skill, "intent": ev.get("intent", ""), "dt": dt, "status": status}
            if skill in seen_skills:
                # Update if we have real status or if this is a primary handoff hit
                if status or not is_seq:
                    ordered[seen_skills[skill]] = entry
            else:
                seen_skills[skill] = len(ordered)
                ordered.append(entry)

    total_tokens = sum(
        int(m.group(1))
        for ev in all_events
        for m in [_re.search(r"tokens=(\d+)", ev.get("reason", ""))]
        if m
    )

    # Entry subtitle: take the reason from the chain-skill's own dispatch event,
    # skipping internal orchestrator housekeeping reasons (chain_initiated, phase=…).
    entry_reason = ""
    for ev in all_events:
        sk = _resolve_chain_skill(ev)
        reason = ev.get("reason", "")
        if sk == chain_skill and reason and "chain_initiated" not in reason and not reason.startswith("phase="):
            entry_reason = reason
            break
    # Fall back to the intent of the first non-empty phase
    if not entry_reason:
        for ev in all_events:
            intent = ev.get("intent", "")
            if intent and intent not in ("execute_chain", "execute_routing_decision"):
                entry_reason = intent.replace("_", " ")
                break

    return {
        "chain_id":    chain_id,
        "chain_skill": chain_skill,
        "started":     first_ts,
        "duration_sec": duration_sec,
        "phases":      ordered,
        "failed_count": sum(1 for p in ordered if p["status"] == "failed"),
        "total_tokens": total_tokens,
        "subtitle":    entry_reason,
        "is_sequence_intent": is_sequence_intent,
    }


def compute_chains(events, chain_defs=None, max_chains: int = 20):
    """Group events into chain summaries, sorted newest-first.

    Strategy 1 — shared chain_id (orchestrate.py --execute path):
        All events with the same chain_id are one chain. The chain-skill name
        comes from the SEQUENCE chain_initiated entry event.

    Strategy 2 — time-window inference (Claude Code direct invocation):
        When a chain-entry SEQUENCE event is followed by events whose skills appear
        in that chain's definition, within a 20-minute window and each with its own
        solo chain_id, merge them under the parent chain. This handles the common
        case where the model calls sub-skills individually without shared chain_id.
    """
    chain_defs = chain_defs or {}
    by_chain = {}
    for ev in events:
        cid = ev.get("chain_id")
        if not cid or not isinstance(cid, str):
            continue
        by_chain.setdefault(cid, []).append(ev)

    # Solo chain_ids: exactly one event (or one start + one complete for same skill)
    solo_ids = {cid for cid, evs in by_chain.items() if len(evs) <= 2}

    # --- Strategy 1: true shared chain_id chains ---
    true_chains = {}  # chain_id -> summary
    for cid, chain_events in by_chain.items():
        is_seq = any(e.get("decision") == "SEQUENCE" for e in chain_events)
        if cid in solo_ids and not is_seq:
            continue
        chain_events = sorted(chain_events, key=lambda e: e.get("timestamp", ""))
        chain_skill = next(
            (_resolve_chain_skill(e) for e in chain_events
             if e.get("decision") == "SEQUENCE" and "chain_initiated" in e.get("reason", "")),
            _resolve_chain_skill(chain_events[0]),
        )
        first_dt = _parse_iso(chain_events[0].get("timestamp", ""))
        s = _build_chain_summary(chain_skill, cid, chain_events, first_dt, chain_defs)
        if s:
            true_chains[cid] = s

    # --- Strategy 2: infer chains from time-window proximity ---
    # Build lookup: which chain_defs contain each skill name
    skill_to_chain = {}
    for chain_name, chain_data in chain_defs.items():
        for ph in chain_data.get("phases", []):
            sk = ph.get("skill")
            if sk:
                skill_to_chain.setdefault(sk, []).append(chain_name)

    # Find entry events: any dispatch to a skill that has a chain_definition,
    # whether it arrived via SEQUENCE+chain_initiated (orchestrate.py) or plain HANDOFF
    # (direct model invocation). The chain_defs key is the canonical identifier.
    entry_events = []
    for cid in solo_ids:
        # If it was already picked up as a true_chain (Strategy 1), don't treat as entry for inference
        if cid in true_chains:
            continue
        for ev in by_chain[cid]:
            skills = extract_logged_skills(ev)
            # Match if ANY skill in the event is a defined chain
            match = next((s for s in skills if s in chain_defs), None)
            if match:
                entry_events.append((ev, cid, match))
                break

    inferred = {}  # chain_name -> merged summary
    claimed_solo_ids = set()  # solo chain_ids absorbed into an inferred chain

    for entry_ev, entry_cid, chain_skill in entry_events:
        defined_skills = {ph.get("skill") for ph in chain_defs.get(chain_skill, {}).get("phases", []) if ph.get("skill")}
        entry_dt = _parse_iso(entry_ev.get("timestamp", ""))
        if not entry_dt:
            continue

        # Collect solo events within 20 minutes whose skill is in this chain's definition
        window_sec = 20 * 60
        related = [entry_ev]
        related_cids = {entry_cid}
        for cid in solo_ids:
            if cid in related_cids or cid in true_chains:
                continue
            for ev in by_chain[cid]:
                ev_skill = ev.get("selected_skill", "")
                if ev_skill not in defined_skills:
                    continue
                ev_dt = _parse_iso(ev.get("timestamp", ""))
                if ev_dt and 0 <= (ev_dt - entry_dt).total_seconds() <= window_sec:
                    related.append(ev)
                    related_cids.add(cid)
                    break

        is_seq = entry_ev.get("decision") == "SEQUENCE"
        if len(related) < 2 and not is_seq:
            continue  # only the entry event and NOT an explicit sequence — skip

        s = _build_chain_summary(chain_skill, entry_cid, related, entry_dt, chain_defs)
        if s:
            inferred[chain_skill + entry_cid] = s
            claimed_solo_ids.update(related_cids)


    # Remaining unclaimed solo chains rendered individually
    solo_chains = {}
    for cid in solo_ids:
        if cid in claimed_solo_ids:
            continue
        chain_events = sorted(by_chain[cid], key=lambda e: e.get("timestamp", ""))
        chain_skill = _resolve_chain_skill(chain_events[0])
        first_dt = _parse_iso(chain_events[0].get("timestamp", ""))
        s = _build_chain_summary(chain_skill, cid, chain_events, first_dt, chain_defs)
        if s:
            solo_chains[cid] = s

    all_chains = list(true_chains.values()) + list(inferred.values())

    # Filter: must be a defined chain
    real_chains = [
        c for c in all_chains
        if c["chain_skill"] in chain_defs
    ]

    real_chains.sort(key=lambda c: c["started"], reverse=True)
    return real_chains[:max_chains]


def load_chain_definitions() -> dict:
    """Load chain_definition.json files from the runtime skills tree.
    Returns {chain_skill_name: {"phases": [...], "description": str}}.
    """
    skills_root = Path.home() / ".agents" / "skills"
    result = {}
    if not skills_root.exists():
        return result
    for skill_dir in sorted(skills_root.iterdir()):
        cd = skill_dir / "config" / "chain_definition.json"
        if not cd.exists():
            continue
        try:
            data = json.loads(cd.read_text(encoding="utf-8"))
            name = data.get("chain_name", skill_dir.name)
            result[name] = {
                "phases":      data.get("phases", []),
                "description": data.get("description", ""),
            }
        except Exception:
            pass
    return result


def render_all_chains_html(chain_defs: dict, skills_counter: Counter = None, chains_counter: Counter = None) -> str:
    """Render all defined chains as blueprint documentation cards."""
    skills_counter = skills_counter or Counter()
    chains_counter = chains_counter or Counter()
    if not chain_defs:
        return '<p style="color:#999;font-size:0.9rem">No chain definitions found in ~/.agents/skills/*/config/chain_definition.json</p>'

    cards = []
    for chain_name, chain_data in sorted(chain_defs.items()):
        phases = chain_data.get("phases", [])
        description = chain_data.get("description", "")
        chain_hits = chains_counter.get(chain_name, 0)

        steps = []
        for i, phase in enumerate(phases):
            phase_skill = phase.get("skill")
            phase_name  = phase.get("name", phase_skill or "agent")
            short = phase_name
            for sep in (" — ", " - "):
                if sep in short:
                    short = short.split(sep, 1)[-1]
            short = short[:36]

            is_agent = phase_skill is None
            note      = html.escape(phase_skill or "agent-handled", quote=True)
            node_cls  = "sn-bp-agent" if is_agent else "sn-bp"
            lbl_cls   = "sl-bp-agent" if is_agent else "sl-bp"
            
            skill_hits = skills_counter.get(phase_skill, 0) if phase_skill else 0
            skill_tag_text = f"{phase_skill} ({skill_hits})" if phase_skill else "agent"
            skill_tag = html.escape(skill_tag_text[:32])
            
            label_html = html.escape(short)
            if phase_skill:
                safe_js_arg = html.escape(json.dumps(phase_skill), quote=True)
                label_html = f'<span class="clickable skill-link" onclick="showDetail({safe_js_arg})">{label_html}</span>'

            conn_html = (
                '<div class="step-conn sc-bp"></div>'
                if i < len(phases) - 1 else ""
            )
            steps.append(
                f'<div class="chain-step-wrap">'
                f'<div class="chain-step">'
                f'<div class="step-node {node_cls}" title="{note}"></div>'
                f'<div class="step-label {lbl_cls}">{label_html}</div>'
                f'<div class="step-skill-tag">{skill_tag}</div>'
                f'</div>'
                f'{conn_html}'
                f'</div>'
            )

        desc_html = (
            f'<p class="chain-def-desc">{html.escape(description)}</p>'
            if description else ""
        )
        cards.append(
            f'<div class="chain-def-card">'
            f'<div class="chain-def-hdr">'
            f'<span class="chain-def-name">{html.escape(chain_name)}</span>'
            f'<span class="chain-def-count">{len(phases)} phases | {chain_hits} hits</span>'
            f'</div>'
            f'{desc_html}'
            f'<div class="chain-track">{"".join(steps)}</div>'
            f'</div>'
        )

    return "\n".join(cards)


def render_chains_section(events, chain_defs=None) -> str:
    """Render Orchestrator Chains section.

    One card per chain. Each card shows the full phase stepper from chain_definition.json
    with status overlaid: green (done), red (failed), amber (agent-handled), grey (not reached).
    """
    chains = compute_chains(events, chain_defs=chain_defs)
    chain_defs = chain_defs or {}

    if not chains:
        return (
            '<div class="card chains-card">'
            '<div class="section-kicker">Chains</div>'
            '<h2>Orchestrator Chains</h2>'
            '<p class="chains-empty">No chains logged yet. Chains appear once '
            '<code>dispatch_cli.py --execute</code> routes to a chain-capable skill '
            '(<code>bug-fix-lifecycle</code>, <code>new-feature-sdlc-skill</code>, …). '
            'All phases share a <code>chain_id</code> and render as a single stepper card.'
            '</p>'
            '</div>'
        )

    cards = []
    for chain in chains:
        cid = chain["chain_id"]
        chain_skill = chain["chain_skill"]
        started = chain["started"][:19]
        dur = chain["duration_sec"]
        dur_label = f"{dur:.1f}s" if dur > 0 else "—"
        failed = chain["failed_count"]
        tokens = chain["total_tokens"]

        badge = (
            f'<span class="chn-badge chn-badge-fail">{failed} failed</span>' if failed
            else '<span class="chn-badge chn-badge-ok">&#10003; done</span>'
        )
        tok_html = f'<span class="chn-tok">{tokens:,} tok</span>' if tokens else ""

        # Build a lookup of executed phases by skill name
        executed = {p["skill"]: p for p in chain["phases"]}

        # Get the full phase list from the chain definition if available
        defined = chain_defs.get(chain_skill, {}).get("phases", [])
        if not defined:
            # No definition: synthesise from executed events only
            defined = [
                {"skill": p["skill"], "name": p["skill"], "id": p["skill"]}
                for p in chain["phases"]
            ]

        # Build stepper steps
        steps = []
        for i, phase_def in enumerate(defined):
            phase_skill = phase_def.get("skill")  # None = agent-handled
            phase_name = phase_def.get("name", phase_skill or "agent")

            # Strip "Step N — " / "Step N - " prefix for display
            short = phase_name
            for sep in (" — ", " - "):
                if sep in short:
                    short = short.split(sep, 1)[-1]
            short = short[:36]

            # Match against executed events
            exec_data = executed.get(phase_skill) if phase_skill else None
            note = html.escape(phase_skill or "agent-handled", quote=True)

            if phase_skill is None:
                node_cls, lbl_cls, time_html = "sn-agent", "sl-agent", ""
            elif exec_data:
                st = exec_data.get("status", "")
                node_cls = "sn-fail" if st == "failed" else "sn-done"
                lbl_cls  = "sl-fail" if st == "failed" else "sl-done"
                dt = exec_data.get("dt", 0)
                time_html = f'<div class="step-time">+{dt:.1f}s</div>'
            else:
                node_cls, lbl_cls, time_html = "sn-pending", "sl-pending", ""

            # Connector after this step (not after the last one)
            conn_done = exec_data is not None and (exec_data.get("status") != "failed")
            conn_html = (
                f'<div class="step-conn {"sc-done" if conn_done else ""}"></div>'
                if i < len(defined) - 1 else ""
            )

            steps.append(
                f'<div class="chain-step-wrap">'
                f'<div class="chain-step">'
                f'<div class="step-node {node_cls}" title="{note}"></div>'
                f'<div class="step-label {lbl_cls}">{html.escape(short)}</div>'
                f'{time_html}'
                f'</div>'
                f'{conn_html}'
                f'</div>'
            )

        n_exec = len([p for p in chain["phases"] if p["skill"] != chain_skill])
        n_total = len(defined)
        progress = f'{n_exec}/{n_total} phases' if n_total > 1 else "1 phase"

        subtitle = chain.get("subtitle", "")
        subtitle_html = (
            f'<div class="chn-subtitle">{html.escape(subtitle)}</div>'
            if subtitle else ""
        )

        safe_chain_skill = html.escape(chain_skill)
        safe_js_arg = html.escape(json.dumps(chain_skill), quote=True)
        chain_link = f'<span class="clickable skill-link" onclick="showDetail({safe_js_arg})">{safe_chain_skill}</span>'

        cards.append(
            f'<div class="chain-card">'
            f'<div class="chn-header">'
            f'<span class="chn-name">{chain_link}</span>'
            f'<span class="chn-id" title="{html.escape(cid)}">{cid[:8]}</span>'
            f'<span class="chn-ts">{html.escape(started)}</span>'
            f'<span class="chn-dur">{html.escape(dur_label)}</span>'
            f'<span class="chn-progress">{progress}</span>'
            f'{tok_html}{badge}'
            f'</div>'
            f'{subtitle_html}'
            f'<div class="chain-track">{"".join(steps)}</div>'
            f'</div>'
        )

    return (
        '<div class="card chains-card collapsible" id="card-chains">'
        '<div class="card-header-toggle" onclick="toggleCard(\'card-chains\')">'
        '<div>'
        '<div class="section-kicker">Chains</div>'
        '<h2>Orchestrator Chains</h2>'
        '</div>'
        '<span class="card-toggle-icon">▾</span>'
        '</div>'
        '<div class="card-content">'
        '<div class="section-heading-row" style="margin-top: 10px;">'
        '<p style="color: var(--muted); font-size: 0.9rem; margin: 0;">Executed multi-phase sequences.</p>'
        '<a href="?view=all-chains" class="all-link">Show all definitions</a>'
        '</div>'
        + "".join(cards)
        + '</div>'
        '</div>'
    )


def main():
    script_dir = Path(__file__).parent.parent
    # SAFE ZONE Discovery & Smart Migration
    persistent_base = Path.home() / ".agents" / "dispatcher-data"
    persistent_log_path = persistent_base / "logs" / "dispatch_events.jsonl"
    local_log_path = script_dir / "logs" / "dispatch_events.jsonl"
    persistent_registry_path = persistent_base / "registry" / "SKILL_REGISTRY.json"
    local_registry_path = script_dir / "registry" / "SKILL_REGISTRY.json"
    
    # Context-Aware Paths
    if ".agents" in str(script_dir.resolve()).lower():
        report_dir = persistent_base / "reports"
        # Auto-Migrate: local logs -> persistent SAFE ZONE
        if local_log_path.exists() and not persistent_log_path.exists():
            persistent_log_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                import shutil
                shutil.copy2(local_log_path, persistent_log_path)
                print(f"[*] Migrated logs to Safe Zone: {persistent_log_path}")
            except Exception: pass
        
        actual_log_path = persistent_log_path if persistent_log_path.exists() else local_log_path
        actual_registry_path = persistent_registry_path if persistent_registry_path.exists() else local_registry_path
    else:
        report_dir = script_dir / "reports"
        actual_log_path = local_log_path if local_log_path.exists() else persistent_log_path
        actual_registry_path = local_registry_path if local_registry_path.exists() else persistent_registry_path

    report_path = report_dir / "wallboard.html"
    staleness_report_path = report_dir / "staleness_report.md"

    if not actual_log_path.exists():
        print(f"[!] No log found at {actual_log_path}. Run migration or log an event first.")
        return

    events = []
    with open(actual_log_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                try:
                    events.append(json.loads(line))
                except Exception:
                    continue
    consulted_at = format_timestamp_for_html(actual_log_path.stat().st_mtime)

    if not events:
        print("[!] Log is empty.")
        return

    registry_index = {}
    if actual_registry_path.exists():
        try:
            with open(actual_registry_path, "r", encoding="utf-8") as f:
                registry_payload = json.load(f)
            registry_index = {
                skill.get("name"): skill
                for skill in registry_payload.get("skills", [])
                if isinstance(skill, dict) and skill.get("name")
            }
        except Exception:
            registry_index = {}

    # Analytics
    total_calls = 0

    # Explode sequences for accurate skill usage counts
    skills_counter = Counter()
    models_counter = Counter()
    for ev in events:
        event_skills = extract_logged_skills(ev)
        total_calls += len(event_skills)
        for skill in event_skills:
            if skill:
                skills_counter[skill] += 1
        models_counter[extract_model_name(ev)] += 1

    most_used = skills_counter.most_common(1)[0] if skills_counter else ("None", 0)
    unique_skills = len(skills_counter)
    
    # Recent activity
    recent = events[-15:][::-1]

    # Treemap weights
    treemap_data = [
        {"name": name, "count": count}
        for name, count in skills_counter.most_common()
    ]

    # Environment Info
    user_name = os.environ.get('USERNAME', 'Unknown User')
    computer_name = platform.node()
    environment_info = f"{computer_name} / {user_name}"

    # Load Staleness Report
    staleness_html = "<i>Staleness report not found. Run scripts/staleness_audit.py first.</i>"
    if staleness_report_path.exists():
        md_content = staleness_report_path.read_text(encoding="utf-8")
        staleness_html = markdown_to_html(md_content)

    # Load Token Cost Reports
    token_cost_items, token_cost_roots = collect_token_cost_reports(script_dir)
    token_cost_html = render_token_cost_table(token_cost_items, token_cost_roots)

    # Decision analytics
    decision_counter = Counter(ev.get("decision", "HANDOFF") for ev in events)
    decision_summary = {
        "H": decision_counter.get("HANDOFF", 0),
        "S": decision_counter.get("SEQUENCE", 0),
        "N": decision_counter.get("NO_MATCH", 0),
        "C": decision_counter.get("CONTEXT_LOAD", 0),
        "P": decision_counter.get("POLICY_CONSULT", 0),
    }
    policy_counter = Counter(
        ev.get("policy_lookup", {}).get("status", "none")
        for ev in events
        if isinstance(ev.get("policy_lookup"), dict)
    )
    policy_summary = {
        "lookups": sum(policy_counter.values()),
        "H": policy_counter.get("hit", 0),
        "M": policy_counter.get("miss", 0),
        "E": policy_counter.get("error", 0),
    }

    # Chain analytics — load definitions so stepper shows all phases, not just executed ones
    chain_defs = load_chain_definitions()

    chains_counter = Counter()
    for ev in events:
        chain_skill = _resolve_chain_skill(ev)
        if chain_skill in chain_defs:
            chains_counter[chain_skill] += 1

    chains_html = render_chains_section(events, chain_defs)
    all_chains_html = render_all_chains_html(chain_defs, skills_counter, chains_counter)

    # Per-skill failure stats: count phase_status occurrences per selected_skill.
    # Skills with no phase_status events at all simply don't display a rate.
    failure_stats: dict[str, list[int]] = {}
    for ev in events:
        status = ev.get("phase_status")
        skill = ev.get("selected_skill")
        if not status or not isinstance(skill, str):
            continue
        bucket = failure_stats.setdefault(skill, [0, 0])  # [fails, total]
        bucket[1] += 1
        if status == "failed":
            bucket[0] += 1
    failure_stats_dict = {k: (v[0], v[1]) for k, v in failure_stats.items()}

    # HTML Generation
    html_content = render_html(
        total_calls=total_calls,
        most_used_name=most_used[0],
        most_used_count=most_used[1],
        unique_skills=unique_skills,
        decision_summary=decision_summary,
        policy_summary=policy_summary,
        recent_events=recent,
        skills_summary=skills_counter.most_common(10),
        all_skills_summary=skills_counter.most_common(),
        models_summary=models_counter.most_common(),
        consulted_at=consulted_at,
        latest_event_at=events[-1].get("timestamp", consulted_at),
        treemap_json=json.dumps(treemap_data),
        all_events_json=json.dumps(events),
        registry_json=json.dumps(registry_index),
        environment_info=environment_info,
        staleness_html=staleness_html,
        chains_html=chains_html,
        all_chains_html=all_chains_html,
        failure_stats_dict=failure_stats_dict,
        token_cost_html=token_cost_html,
        token_cost_count=len(token_cost_items),
    )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"[*] Integrated wallboard generated at: {report_path}")

def markdown_to_html(md: str) -> str:
    """Basic markdown to HTML converter for staleness report."""
    import re
    lines = md.splitlines()
    html = []
    in_table = False
    
    for line in lines:
        line = line.strip()
        if not line:
            if in_table:
                html.append("</table>")
                in_table = False
            continue

        # Headers
        if line.startswith("### "):
            html.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "):
            html.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            html.append(f"<h1>{line[2:]}</h1>")
        
        # Tables
        elif "|" in line:
            if not in_table:
                html.append('<table class="audit-table">')
                in_table = True
            
            # Skip separator lines
            if "---" in line and "|" in line:
                continue
                
            cells = [center.strip() for center in line.split("|") if center.strip() or center == " "]
            if not cells: continue
            
            tag = "td"
            # Logic to detect header row: if it's the first row and the next one is a separator
            # But here we just simplified
            
            row_html = "<tr>" + "".join([f"<{tag}>{c}</{tag}>" for c in cells]) + "</tr>"
            html.append(row_html)
        
        # Lists
        elif line.startswith("- ") or line.startswith("* "):
            html.append(f"<li>{line[2:]}</li>")
        elif re.match(r'^\d+\.', line):
            html.append(f"<li>{line[line.find('.')+1:].strip()}</li>")
            
        # Paragraphs / Bold
        else:
            line = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', line)
            line = re.sub(r'`(.*?)`', r'<code>\1</code>', line)
            html.append(f"<p>{line}</p>")
            
    if in_table:
        html.append("</table>")
        
    return "\n".join(html)

def render_html(total_calls, most_used_name, most_used_count, unique_skills, decision_summary, policy_summary, recent_events, skills_summary, all_skills_summary, consulted_at, latest_event_at, treemap_json, all_events_json, registry_json, environment_info, staleness_html, chains_html="", token_cost_html=None, token_cost_count=0, models_summary=None, failure_stats_dict=None, all_chains_html=""):
    leaderboard_html = "".join([
        render_skill_count_row(rank, name, count)
        for rank, (name, count) in enumerate(skills_summary, start=1)
    ])

    _MODEL_TOP_N = 5
    if models_summary:
        top_models = models_summary[:_MODEL_TOP_N]
        model_hits_rows = "".join(
            render_model_count_row(rank, name, count)
            for rank, (name, count) in enumerate(top_models, start=1)
        )
        all_model_rows = "".join(
            render_model_count_row(rank, name, count)
            for rank, (name, count) in enumerate(models_summary, start=1)
        )
        show_all_models_link = (
            f'<a href="?view=all-models" class="all-link">(All {len(models_summary)})</a>'
            if len(models_summary) > _MODEL_TOP_N else ""
        )
    else:
        model_hits_rows = '<div class="muted-cell" style="padding: 12px 0;">No model telemetry yet.</div>'
        all_model_rows = model_hits_rows
        show_all_models_link = ""
    model_hits_html = (
        '<div class="card">'
        '<div class="section-kicker">Distribution</div>'
        '<div class="section-heading-row">'
        '<h2>Hits per Model</h2>'
        f'{show_all_models_link}'
        '</div>'
        f'{model_hits_rows}'
        '</div>'
    )
    all_models_html = (
        f'<div class="section-kicker">Complete Model Leaderboard</div>'
        f'{all_model_rows}'
    )

    timeline_html = (
        '<div class="table-container recent-activity-shell">'
        '<table class="recent-activity-table">'
        '<thead>'
        '<tr>'
        '<th>Time</th>'
        '<th>Type</th>'
        '<th>Model</th>'
        '<th>Primary Skill</th>'
        '<th>Secondary Skills</th>'
        '<th>Intent</th>'
        '<th>Policy</th>'
        '</tr>'
        '</thead>'
        '<tbody>'
        + "".join(render_recent_activity(event) for event in recent_events)
        + '</tbody></table></div>'
    )

    all_skills_html = (
        '<div class="section-kicker">Complete Leaderboard</div>'
        + "".join(
            render_skill_count_row(rank, name, count, failure_stats=failure_stats_dict)
            for rank, (name, count) in enumerate(all_skills_summary, start=1)
        )
    )

    decision_markup = (
        f'<div class="stat-value stat-composite">'
        f'<span class="tone-olive" title="HANDOFF">{decision_summary["H"]}</span>'
        f'<span class="divider">/</span>'
        f'<span class="tone-gold" title="SEQUENCE">{decision_summary["S"]}</span>'
        f'<span class="divider">/</span>'
        f'<span class="tone-muted" title="NO_MATCH">{decision_summary["N"]}</span>'
        f'</div>'
        f'<div class="stat-composite stat-sub-row">'
        f'<span style="color:var(--accent)" title="CONTEXT_LOAD">&#128218; {decision_summary.get("C", 0)}</span>'
        f'<span class="divider"> / </span>'
        f'<span style="color:var(--accent-soft, #9b6)" title="POLICY_CONSULT">&#128203; {decision_summary.get("P", 0)}</span>'
        f'</div>'
    )

    policy_markup = (
        f'<div class="stat-value stat-composite">'
        f'<span class="tone-olive">{policy_summary["H"]}</span>'
        f'<span class="divider">/</span>'
        f'<span class="tone-gold">{policy_summary["M"]}</span>'
        f'<span class="divider">/</span>'
        f'<span class="tone-muted">{policy_summary["E"]}</span>'
        f'</div>'
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="refresh" content="30">
    <title>Skill Dispatcher Wallboard & Radiator</title>
    <script>
        // Restore view from URL before first paint to prevent flash of default dashboard
        // when the meta refresh reloads the page on a sub-view.
        (function () {{
            try {{
                if ('scrollRestoration' in history) history.scrollRestoration = 'auto';
                var view = new URLSearchParams(location.search).get('view');
                var map = {{
                    'wallboard': 'radiator-mode',
                    'detail': 'detail-mode',
                    'all-activity': 'all-activity-mode',
                    'staleness': 'staleness-mode',
                    'token-cost': 'token-cost-mode'
                }};
                if (map[view]) document.documentElement.dataset.initialView = map[view];
            }} catch (e) {{ /* ignore */ }}
        }})();
    </script>
    <style>
        html[data-initial-view] {{ visibility: hidden; }}
        html.view-ready {{ visibility: visible; }}
    </style>
    <style>
        :root {{
            --bg: #efe4d1;
            --paper: rgba(255, 251, 243, 0.82);
            --paper-strong: #fffaf2;
            --ink: #18130f;
            --muted: #756858;
            --line: rgba(98, 73, 42, 0.16);
            --line-strong: rgba(98, 73, 42, 0.26);
            --accent: #a34e25;
            --accent-strong: #7f3817;
            --accent-soft: rgba(163, 78, 37, 0.10);
            --olive: #42563d;
            --gold: #c3922f;
            --shadow: 0 22px 60px rgba(73, 47, 18, 0.10);
            --radius: 22px;
            --radius-lg: 34px;
        }}

        * {{ box-sizing: border-box; }}
        body {{
            margin: 0;
            min-height: 100vh;
            background:
                radial-gradient(circle at 12% 18%, rgba(255, 245, 222, 0.95), transparent 26%),
                radial-gradient(circle at 85% 14%, rgba(211, 164, 107, 0.18), transparent 20%),
                radial-gradient(circle at 74% 62%, rgba(255, 255, 255, 0.54), transparent 22%),
                linear-gradient(180deg, #f6eedf 0%, #ede2cf 48%, #e9dcc8 100%);
            color: var(--ink);
            font-family: "Aptos", "Trebuchet MS", "Segoe UI", sans-serif;
            line-height: 1.5;
            transition: background 0.3s ease;
        }}

        body::before {{
            content: "";
            position: fixed;
            inset: 0;
            pointer-events: none;
            background-image:
                linear-gradient(rgba(120, 89, 53, 0.025) 1px, transparent 1px),
                linear-gradient(90deg, rgba(120, 89, 53, 0.025) 1px, transparent 1px);
            background-size: 120px 120px;
            opacity: 0.45;
            mix-blend-mode: multiply;
        }}

        .container {{
            position: relative;
            width: 100%;
            max-width: none;
            margin: 0;
            padding: 24px 34px 48px;
            transition: opacity 0.3s ease;
        }}

        /* Sidebar Navigation */
        .sidebar {{
            position: fixed;
            left: 0;
            top: 0;
            bottom: 0;
            width: 280px;
            background: linear-gradient(180deg, #1e1b18 0%, #12100e 100%);
            color: #fffaf0;
            z-index: 5000;
            padding: 34px 20px;
            display: flex;
            flex-direction: column;
            gap: 40px;
            box-shadow: 10px 0 30px rgba(0,0,0,0.15);
            border-right: 1px solid rgba(255,255,255,0.05);
            transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }}

        .sidebar.collapsed {{
            width: 80px;
            padding: 34px 12px;
            align-items: center;
        }}

        .sidebar.collapsed .brand-text,
        .sidebar.collapsed .nav-item span:not(.nav-icon) {{
            display: none;
        }}

        .sidebar.collapsed .sidebar-brand {{
            padding: 0;
            justify-content: center;
        }}

        .sidebar.collapsed .nav-item {{
            padding: 14px 0;
            justify-content: center;
            width: 100%;
        }}

        .sidebar-toggle {{
            position: absolute;
            right: -14px;
            top: 40px;
            width: 28px;
            height: 28px;
            background: var(--accent);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            color: white;
            font-size: 14px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.2);
            z-index: 5001;
            transition: transform 0.3s ease;
        }}

        .sidebar.collapsed .sidebar-toggle {{
            transform: rotate(180deg);
        }}

        .sidebar-brand {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 0 14px;
        }}

        .brand-dot {{
            width: 14px;
            height: 14px;
            background: var(--accent);
            border-radius: 50%;
            box-shadow: 0 0 15px var(--accent);
        }}

        .brand-text {{
            font-family: "Baskerville Old Face", serif;
            font-size: 1.4rem;
            letter-spacing: -0.02em;
        }}

        .nav-menu {{
            display: flex;
            flex-direction: column;
            gap: 8px;
            list-style: none;
            padding: 0;
            margin: 0;
        }}

        .nav-item {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 14px 18px;
            border-radius: 14px;
            color: rgba(255,255,255,0.6);
            text-decoration: none;
            font-weight: 600;
            font-size: 0.95rem;
            transition: all 0.2s ease;
            cursor: pointer;
        }}

        .nav-item:hover {{
            color: #fff;
            background: rgba(255,255,255,0.05);
        }}

        .nav-item.active {{
            color: #fff;
            background: var(--accent);
            box-shadow: 0 8px 20px rgba(163, 78, 37, 0.3);
        }}

        .nav-icon {{
            font-size: 1.2rem;
            width: 24px;
            text-align: center;
        }}

        /* Content Adjustment for Sidebar */
        .container, 
        .detail-shell, 
        .all-activity-shell, 
        .all-models-shell, 
        .all-chains-shell, 
        .staleness-shell, 
        .token-cost-shell {{
            padding-left: 314px !important; /* sidebar width + padding */
            transition: padding-left 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }}
        
        .wall-shell {{
            padding-left: 300px !important;
            transition: padding-left 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }}

        body.sidebar-collapsed .container,
        body.sidebar-collapsed .detail-shell,
        body.sidebar-collapsed .all-activity-shell,
        body.sidebar-collapsed .all-models-shell,
        body.sidebar-collapsed .all-chains-shell,
        body.sidebar-collapsed .staleness-shell,
        body.sidebar-collapsed .token-cost-shell {{
            padding-left: 114px !important;
        }}

        body.sidebar-collapsed .wall-shell {{
            padding-left: 100px !important;
        }}

        /* Collapsible Cards */
        .card-header-toggle {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            cursor: pointer;
            user-select: none;
        }}

        .card-toggle-icon {{
            font-size: 1.2rem;
            transition: transform 0.3s ease;
            color: var(--muted);
            opacity: 0.5;
        }}

        .card.collapsed .card-toggle-icon {{
            transform: rotate(-90deg);
        }}

        .card-content {{
            transition: max-height 0.3s ease, opacity 0.3s ease, margin-top 0.3s ease;
            max-height: 10000px;
            opacity: 1;
            overflow: hidden;
        }}

        .card.collapsed .card-content {{
            max-height: 0;
            opacity: 0;
            margin-top: 0 !important;
            pointer-events: none;
        }}
        
        .card.collapsed h2 {{
            margin-bottom: 0;
        }}

        header {{
            position: relative;
            margin-bottom: 34px;
            display: grid;
            grid-template-columns: minmax(0, 1.4fr) 420px;
            gap: 24px;
            align-items: stretch;
            padding: 30px 30px 28px;
            border: 1px solid rgba(120, 89, 53, 0.14);
            border-radius: var(--radius-lg);
            background:
                linear-gradient(135deg, rgba(255, 251, 243, 0.92), rgba(244, 233, 214, 0.70)),
                rgba(255, 255, 255, 0.68);
            box-shadow: var(--shadow);
            overflow: hidden;
        }}

        header::before {{
            content: "";
            position: absolute;
            inset: 0;
            background:
                radial-gradient(circle at top right, rgba(163, 78, 37, 0.12), transparent 24%),
                linear-gradient(90deg, rgba(255,255,255,0.32), transparent 46%);
            pointer-events: none;
        }}

        .hero-copy,
        .view-controls {{
            position: relative;
            z-index: 1;
        }}

        .eyebrow {{
            display: inline-flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 14px;
            color: var(--accent-strong);
            font-size: 0.78rem;
            font-weight: 800;
            letter-spacing: 0.16em;
            text-transform: uppercase;
        }}

        .eyebrow::before {{
            content: "";
            display: block;
            width: 40px;
            height: 1px;
            background: rgba(127, 56, 23, 0.4);
        }}

        h1 {{
            font-family: "Baskerville Old Face", "Palatino Linotype", Georgia, serif;
            font-size: clamp(2.8rem, 5vw, 4.7rem);
            margin: 0;
            letter-spacing: -0.05em;
            line-height: 0.94;
        }}

        .hero-subcopy {{
            max-width: 70ch;
            margin-top: 14px;
            color: rgba(24, 19, 15, 0.74);
            font-size: 1rem;
        }}

        .timestamp {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px 14px;
            color: var(--muted);
            font-size: 0.83rem;
            margin-top: 18px;
            text-transform: uppercase;
            letter-spacing: 0.12em;
        }}

        .view-controls {{
            display: grid;
            gap: 16px;
            align-content: center;
        }}

        .btn {{
            position: relative;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-height: 58px;
            padding: 0 24px;
            border-radius: 999px;
            border: 1px solid rgba(72, 63, 53, 0.12);
            background: linear-gradient(180deg, #fffdfa 0%, #f6efe5 100%);
            box-shadow: 0 2px 0 rgba(72, 63, 53, 0.05), 0 10px 18px rgba(72, 63, 53, 0.08);
            font-weight: 800;
            font-size: 1.02rem;
            letter-spacing: 0.01em;
            cursor: pointer;
            transition: transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease, color 0.18s ease, border-color 0.18s ease;
            color: var(--ink);
            text-decoration: none;
        }}

        .btn::after {{
            content: "";
            position: absolute;
            inset: 1px;
            border-radius: inherit;
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.45), rgba(255, 255, 255, 0));
            pointer-events: none;
        }}

        .btn:hover {{
            transform: translateY(-2px);
            border-color: rgba(170, 75, 34, 0.28);
            box-shadow: 0 4px 0 rgba(72, 63, 53, 0.04), 0 16px 24px rgba(170, 75, 34, 0.18);
        }}

        .btn:focus-visible {{
            outline: 3px solid rgba(170, 75, 34, 0.22);
            outline-offset: 3px;
        }}

        .btn-primary {{
            background: linear-gradient(135deg, #aa4b22 0%, #c45b2f 100%);
            color: #fffaf1;
            border-color: rgba(170, 75, 34, 0.3);
            box-shadow: 0 2px 0 rgba(120, 50, 20, 0.15), 0 14px 24px rgba(170, 75, 34, 0.18);
        }}

        .btn-primary:hover {{
            color: #ffffff;
            background: linear-gradient(135deg, #96401d 0%, #aa4b22 100%);
            box-shadow: 0 4px 0 rgba(120, 50, 20, 0.14), 0 18px 28px rgba(170, 75, 34, 0.24);
        }}

        .btn-secondary {{
            background: linear-gradient(180deg, #fffdfa 0%, #f5ede2 100%);
        }}

        .btn-secondary:hover {{
            color: var(--ink);
            background: linear-gradient(180deg, #fff7ef 0%, #f2e6d6 100%);
        }}

        .info-trigger {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 34px;
            height: 34px;
            background: linear-gradient(135deg, var(--accent), #c56c3b);
            color: white;
            border-radius: 50%;
            font-size: 18px;
            font-weight: bold;
            cursor: pointer;
            margin-left: 12px;
            vertical-align: middle;
            box-shadow: 0 12px 22px rgba(163, 78, 37, 0.22);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }}

        .info-trigger:hover {{
            transform: translateY(-1px) scale(1.06);
            box-shadow: 0 16px 30px rgba(163, 78, 37, 0.28);
        }}

        .info-box {{
            display: none;
            background: linear-gradient(180deg, rgba(255,255,255,0.95), rgba(251, 244, 235, 0.92));
            border: 1px solid var(--line);
            border-radius: 20px;
            padding: 22px 24px;
            margin-top: 18px;
            font-size: 0.95rem;
            line-height: 1.7;
            color: var(--ink);
            box-shadow: var(--shadow);
        }}

        .info-box.active {{ display: block; }}
        .info-box strong {{ color: var(--accent); }}

        .grid {{
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(300px, 1.28fr) minmax(0, 1fr) minmax(0, 1fr);
            gap: 18px;
            margin-bottom: 26px;
        }}

        .card {{
            position: relative;
            background: linear-gradient(180deg, rgba(255, 251, 243, 0.94), rgba(250, 241, 229, 0.80));
            border: 1px solid rgba(120, 89, 53, 0.12);
            border-radius: var(--radius);
            padding: 26px;
            box-shadow: var(--shadow);
            backdrop-filter: blur(10px);
            overflow: hidden;
        }}

        .card::before {{
            content: "";
            position: absolute;
            inset: 0 auto auto 0;
            width: 100%;
            height: 3px;
            background: linear-gradient(90deg, rgba(163, 78, 37, 0.65), rgba(195, 146, 47, 0.12));
            opacity: 0.72;
        }}

        .stat-label {{
            color: var(--muted);
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            margin-bottom: 8px;
            display: block;
        }}

        .stat-value {{
            font-size: clamp(3rem, 4vw, 4.3rem);
            font-weight: 800;
            line-height: 0.95;
            margin-top: 14px;
            letter-spacing: -0.06em;
        }}

        .stat-card {{
            min-height: 182px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }}

        .stat-foot {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-top: 18px;
            color: var(--muted);
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
        }}

        .stat-foot::before {{
            content: "";
            flex: 1;
            height: 1px;
            margin-right: 12px;
            background: linear-gradient(90deg, rgba(117, 104, 88, 0.35), transparent);
        }}

        .stat-composite {{
            display: flex;
            align-items: baseline;
            gap: 0.08em;
            white-space: nowrap;
        }}

        .stat-sub-row {{
            font-size: 1rem;
            gap: 0.3em;
            margin-top: 4px;
            opacity: 0.85;
        }}

        .divider {{
            color: rgba(117, 104, 88, 0.6);
            margin: 0 0.02em;
        }}

        .tone-olive {{ color: var(--olive); }}
        .tone-gold {{ color: var(--gold); }}
        .tone-muted {{ color: var(--muted); }}

        .snapshot-banner {{
            margin: 22px 0 0;
            padding: 18px 20px;
            border-radius: 18px;
            border: 1px solid rgba(197, 139, 42, 0.28);
            background: linear-gradient(180deg, rgba(197, 139, 42, 0.12), rgba(197, 139, 42, 0.05));
            color: #5f4915;
            font-size: 1rem;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.35);
        }}

        .snapshot-banner strong {{
            color: #6d4c05;
        }}

        .snapshot-banner.alert {{
            border-color: rgba(170, 75, 34, 0.32);
            background: linear-gradient(180deg, rgba(170, 75, 34, 0.14), rgba(170, 75, 34, 0.06));
            color: #6e2e14;
        }}

        .main-content {{
            display: grid;
            grid-template-columns: minmax(250px, 0.72fr) minmax(0, 1.75fr);
            row-gap: 26px;
            column-gap: 18px;
            align-items: start;
        }}

        .left-col {{
            display: flex;
            flex-direction: column;
            gap: 26px;
            align-self: start;
        }}
        .main-content > .recent-activity-card {{
            grid-column: 2;
        }}

        h2 {{
            font-family: "Baskerville Old Face", "Palatino Linotype", Georgia, serif;
            font-size: 2.2rem;
            margin-top: 0;
            margin-bottom: 22px;
            letter-spacing: -0.04em;
        }}

        .section-heading-row {{
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            gap: 16px;
            margin-bottom: 22px;
        }}

        .section-heading-row h2 {{
            margin-bottom: 0;
        }}

        .all-link {{
            color: var(--accent);
            font-size: 0.92rem;
            font-weight: 800;
            text-decoration: underline dotted;
            text-underline-offset: 4px;
            white-space: nowrap;
        }}

        .section-kicker {{
            margin-bottom: 10px;
            color: var(--muted);
            font-size: 0.74rem;
            font-weight: 800;
            letter-spacing: 0.16em;
            text-transform: uppercase;
        }}

        .rank-row {{
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            gap: 16px;
            padding: 14px 0;
            border-bottom: 1px solid var(--line);
        }}

        .rank-row strong {{
            font-size: 1.35rem;
            letter-spacing: -0.04em;
        }}

        .all-skill-row {{
            display: grid;
            grid-template-columns: 44px minmax(0, 1fr) minmax(72px, auto);
            align-items: center;
        }}

        .rank-index {{
            color: var(--muted);
            font-size: 0.86rem;
            font-weight: 800;
            font-variant-numeric: tabular-nums;
        }}

        .all-skill-name {{
            min-width: 0;
        }}

        .all-skills-card {{
            width: 100%;
            max-width: none !important;
            margin: 0;
        }}

        .badge {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 36px;
            height: 36px;
            border-radius: 12px;
            font-size: 0.7rem;
            font-weight: 800;
            color: white;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.18);
        }}

        .badge.handoff {{ background: var(--olive); }}
        .badge.sequence {{ background: var(--gold); }}
        .badge.no_match {{ background: var(--muted); }}

        .recent-activity-shell {{
            background: linear-gradient(180deg, rgba(255,255,255,0.52), rgba(253,248,241,0.76));
            border-radius: 18px;
            border: 1px solid rgba(120, 89, 53, 0.1);
        }}

        /* ── Orchestrator Chains ───────────────────────────────────── */
        .chains-card {{ margin-top: 0; width: 100%; box-sizing: border-box; grid-column: 1 / -1; }}
        .chains-empty {{ color:#999; font-size:0.88rem; margin:12px 0 0; }}
        .chain-card {{
            border: 1px solid rgba(120,89,53,0.13);
            border-radius: 14px;
            padding: 14px 18px 16px;
            margin-bottom: 14px;
            background: rgba(255,255,255,0.62);
            width: 100%;
            box-sizing: border-box;
        }}
        /* Header row */
        .chn-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
            margin-bottom: 16px;
        }}
        .chn-name {{
            font-weight: 800;
            font-size: 1.05rem;
            color: #1a237e;
            flex: 1;
            min-width: 120px;
            word-break: break-word;
        }}
        .chn-id {{
            font-family: 'Consolas','Menlo',monospace;
            font-size: 0.72rem;
            font-weight: 700;
            color: #1565c0;
            background: rgba(33,150,243,0.1);
            padding: 2px 8px;
            border-radius: 4px;
        }}
        .chn-subtitle {{
            font-size: 0.82rem;
            color: #6d4c41;
            font-style: italic;
            margin: -8px 0 12px;
            opacity: 0.85;
        }}
        .chn-ts    {{ color:#999; font-size:0.76rem; }}
        .chn-dur   {{ color:#2e7d32; font-weight:700; font-size:0.82rem; }}
        .chn-progress {{ color:#999; font-size:0.74rem; }}
        .chn-tok   {{ color:#aaa; font-size:0.72rem; }}
        .chn-badge {{
            font-size: 0.72rem;
            font-weight: 700;
            padding: 3px 10px;
            border-radius: 20px;
        }}
        .chn-badge-ok   {{ background:rgba(46,125,50,0.1); color:#2e7d32; }}
        .chn-badge-fail {{ background:rgba(183,28,28,0.1); color:#b71c1c; }}
        /* Stepper track */
        .chain-track {{
            display: flex;
            align-items: flex-start;
            overflow-x: auto;
            padding-bottom: 4px;
            scrollbar-width: thin;
        }}
        .chain-step-wrap {{
            display: flex;
            align-items: flex-start;
            flex-shrink: 0;
        }}
        .chain-step {{
            display: flex;
            flex-direction: column;
            align-items: center;
            width: 108px;
            flex-shrink: 0;
        }}
        /* Node circle */
        .step-node {{
            width: 18px;
            height: 18px;
            border-radius: 50%;
            border: 2px solid #d0ccc7;
            background: #f0ede8;
            flex-shrink: 0;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }}
        .sn-done    {{ background:#43a047; border-color:#2e7d32; }}
        .sn-fail    {{ background:#e53935; border-color:#b71c1c; }}
        .sn-agent   {{ background:#fb8c00; border-color:#e65100; }}
        .sn-pending {{ background:#f0ede8; border-color:#d0ccc7; }}
        /* Connector line between nodes — flex:1 so it stretches to fill available card width */
        .step-conn {{
            height: 2px;
            background: #ddd;
            flex: 1;
            min-width: 20px;
            margin-top: 8px;
        }}
        .sc-done {{ background:#43a047; }}
        /* Step labels */
        .step-label {{
            font-size: 0.63rem;
            text-align: center;
            margin-top: 5px;
            max-width: 108px;
            word-break: break-word;
            line-height: 1.3;
            color: #bbb;
        }}
        .sl-done    {{ color:#2e7d32; font-weight:600; }}
        .sl-fail    {{ color:#b71c1c; font-weight:600; }}
        .sl-agent   {{ color:#e65100; }}
        .sl-pending {{ color:#bbb; }}
        .step-time  {{
            font-size: 0.57rem;
            color: #43a047;
            text-align: center;
            font-family: 'Consolas','Menlo',monospace;
            margin-top: 2px;
        }}
        /* Blueprint (chain definition) styles */
        .sn-bp       {{ background:#e3f2fd; border-color:#1565c0; }}
        .sn-bp-agent {{ background:#fff3e0; border-color:#e65100; }}
        .sl-bp       {{ color:#1565c0; font-weight:600; }}
        .sl-bp-agent {{ color:#e65100; }}
        .sc-bp       {{ background:#90caf9; }}
        .step-skill-tag {{
            font-size: 0.52rem;
            color: #aaa;
            text-align: center;
            font-family: 'Consolas','Menlo',monospace;
            margin-top: 2px;
            max-width: 108px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .chain-def-card {{
            border: 1px solid rgba(21,101,192,0.15);
            border-radius: 14px;
            padding: 16px 20px 18px;
            margin-bottom: 18px;
            background: rgba(227,242,253,0.25);
        }}
        .chain-def-hdr {{
            display: flex;
            align-items: center;
            gap: 14px;
            margin-bottom: 10px;
        }}
        .chain-def-name {{ font-weight:800; font-size:1.1rem; color:#1a237e; }}
        .chain-def-count {{ color:#888; font-size:0.78rem; }}
        .chain-def-desc  {{
            font-size: 0.82rem;
            color: #5d4037;
            font-style: italic;
            margin: 0 0 14px;
            opacity: 0.85;
        }}

        .failure-rate {{
            display: inline-block;
            margin-left: 8px;
            padding: 1px 8px;
            border-radius: 4px;
            font-size: 0.7rem;
            font-weight: 700;
            letter-spacing: 0.02em;
            background: rgba(0, 0, 0, 0.04);
        }}
        .failure-rate.tone-red {{ background: rgba(216, 27, 96, 0.12); color: #b71c1c; }}
        .failure-rate.tone-gold {{ background: rgba(249, 168, 37, 0.14); color: #6d4c41; }}
        .failure-rate.tone-muted {{ background: rgba(46, 125, 50, 0.10); color: #2e7d32; }}

        .recent-activity-table th:nth-child(1) {{ width: 132px; }}
        .recent-activity-table th:nth-child(2) {{ width: 64px; text-align: center; }}
        .recent-activity-table th:nth-child(3) {{ width: 220px; }}
        .recent-activity-table th:nth-child(4) {{ width: 170px; }}
        .recent-activity-table th:nth-child(5) {{ width: 180px; }}
        .recent-activity-table th:nth-child(6) {{ width: 360px; }}
        .recent-activity-table th:nth-child(7) {{ width: 180px; }}
        .recent-activity-table td:nth-child(2) {{ text-align: center; }}

        .recent-time-cell {{ color: var(--muted); font-size: 0.88rem; line-height: 1.25; font-variant-numeric: tabular-nums; white-space: nowrap; }}
        .recent-time-cell > div {{ white-space: nowrap; }}
        .recent-time-cell small {{ opacity: 0.8; white-space: nowrap; }}
        .skill-link {{ font-weight: 700; color: var(--accent); }}
        .secondary-skills-cell {{ font-size: 0.96rem; }}
        .policy-cell {{ font-size: 0.84rem; }}
        .recent-intent-cell {{
            font-size: 0.96rem;
            max-width: 0;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .policy-pill {{
            display: inline-flex;
            align-items: center;
            padding: 8px 12px;
            border-radius: 999px;
            background: linear-gradient(180deg, rgba(163, 78, 37, 0.12), rgba(163, 78, 37, 0.05));
            color: var(--accent);
            font-weight: 700;
            font-size: 0.8rem;
            letter-spacing: 0.01em;
        }}

        .muted-cell {{ color: var(--muted); font-style: italic; }}

        .model-badge {{
            display: inline-flex;
            align-items: center;
            max-width: 100%;
            gap: 10px;
            padding: 7px 10px 7px 7px;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.62);
            border: 1px solid rgba(120, 89, 53, 0.13);
            color: var(--ink);
            font-weight: 700;
            line-height: 1.1;
        }}

        .vendor-logo {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            flex: 0 0 auto;
            width: 30px;
            height: 30px;
            border-radius: 999px;
            color: white;
            font-size: 0.64rem;
            font-weight: 900;
            letter-spacing: 0;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.22);
        }}

        .vendor-icon {{
            width: 17px;
            height: 17px;
            object-fit: contain;
            filter: invert(1);
        }}

        .vendor-fallback {{
            display: none;
        }}

        .model-name {{
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}

        .vendor-unknown .vendor-fallback {{
            display: inline;
        }}

        .vendor-openai .vendor-logo {{ background: #111111; }}
        .vendor-anthropic .vendor-logo {{ background: #543f32; }}
        .vendor-google .vendor-logo {{ background: linear-gradient(135deg, #4285f4, #34a853 48%, #fbbc04 76%, #ea4335); }}
        .vendor-meta .vendor-logo {{ background: #0866ff; }}
        .vendor-mistral .vendor-logo {{ background: #f06f2f; }}
        .vendor-xai .vendor-logo {{ background: #222222; }}
        .vendor-deepseek .vendor-logo {{ background: #4a69ff; }}
        .vendor-cohere .vendor-logo {{ background: #39594d; }}
        .vendor-unknown {{
            color: var(--muted);
        }}
        .vendor-unknown .vendor-logo {{ background: #9b8c7a; }}

        .integrity-card {{
            padding: 16px 18px;
            border-radius: 24px;
            border: 1px solid rgba(66, 86, 61, 0.14);
            background: linear-gradient(180deg, rgba(247, 244, 237, 0.95), rgba(240, 235, 226, 0.9));
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.65);
        }}

        .integrity-label {{
            display: block;
            margin-bottom: 10px;
            color: var(--muted);
            font-size: 0.72rem;
            font-weight: 800;
            letter-spacing: 0.14em;
            text-transform: uppercase;
        }}

        .integrity-value {{
            display: inline-flex;
            align-items: center;
            gap: 10px;
            color: var(--olive);
            font-weight: 800;
            font-size: 1.05rem;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }}

        .integrity-dot {{
            width: 12px;
            height: 12px;
            border-radius: 999px;
            background: radial-gradient(circle at 35% 35%, #9eb39c, var(--olive));
            box-shadow: 0 0 0 6px rgba(66, 86, 61, 0.08);
        }}

        .environment-block {{
            margin-top: 34px;
            padding-top: 18px;
            border-top: 1px solid var(--line);
        }}

        .clickable {{
            cursor: pointer;
            text-decoration: underline dotted;
            text-underline-offset: 4px;
        }}

        .clickable:hover {{
            color: var(--accent);
        }}

        .wall-shell {{
            display: none;
            position: fixed;
            inset: 0;
            background:
                radial-gradient(circle at top right, rgba(163, 78, 37, 0.10), transparent 20%),
                linear-gradient(180deg, #f3e8d7 0%, #eadbc4 100%);
            z-index: 1000;
            padding: 20px;
            flex-direction: column;
            overflow: hidden;
        }}

        body.radiator-mode .container {{ display: none; }}
        body.radiator-mode .wall-shell {{ display: flex; }}

        .wall-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }}

        .wall-grid-container {{
            flex: 1;
            position: relative;
            background: rgba(0,0,0,0.03);
            border-radius: 20px;
            overflow: hidden;
            border: 2px solid var(--line);
        }}

        .wall-tile {{
            position: absolute;
            background: var(--paper-strong);
            border: 1px solid var(--line);
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            padding: 10px;
            transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1);
            overflow: hidden;
            box-shadow: 0 4px 15px rgba(0,0,0,0.05);
        }}

        .wall-tile:hover {{
            z-index: 10;
            transform: scale(1.02);
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            background: white;
        }}

        .wall-tile .tile-title {{
            font-family: "Baskerville Old Face", "Palatino Linotype", Georgia, serif;
            font-weight: 800;
            text-align: center;
            color: var(--accent);
            line-height: 1;
            margin-bottom: 5px;
        }}

        .wall-tile .tile-count {{
            color: var(--muted);
            font-weight: 700;
            font-size: 1.2rem;
        }}

        .detail-shell,
        .all-activity-shell,
        .all-models-shell,
        .all-chains-shell,
        .staleness-shell,
        .token-cost-shell {{
            display: none;
            position: fixed;
            inset: 0;
            background:
                radial-gradient(circle at top left, rgba(255,255,255,0.46), transparent 20%),
                linear-gradient(180deg, #f3e8d7 0%, #eadbc4 100%);
            z-index: 2000;
            padding: 48px clamp(24px, 4vw, 60px);
            overflow-y: auto;
        }}

        /* Clean Shell Headers (removing pane-in-pane feel) */
        .shell-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 34px;
            padding-bottom: 20px;
            border-bottom: 2px solid rgba(120, 89, 53, 0.15);
        }}

        .shell-header h1 {{
            margin: 0;
            font-size: 3rem;
        }}

        body.detail-mode .container, body.detail-mode .wall-shell {{ display: none; }}
        body.detail-mode .detail-shell {{ display: block; }}
        body.all-activity-mode .container, body.all-activity-mode .wall-shell {{ display: none; }}
        body.all-activity-mode .all-activity-shell {{ display: block; }}
        body.all-models-mode .container, body.all-models-mode .wall-shell {{ display: none; }}
        body.all-models-mode .all-models-shell {{ display: block; }}
        body.all-chains-mode .container, body.all-chains-mode .wall-shell {{ display: none; }}
        body.all-chains-mode .all-chains-shell {{ display: block; }}
        body.staleness-mode .container, body.staleness-mode .wall-shell {{ display: none; }}
        body.staleness-mode .staleness-shell {{ display: block; }}
        body.token-cost-mode .container, body.token-cost-mode .wall-shell {{ display: none; }}
        body.token-cost-mode .token-cost-shell {{ display: block; }}

        .detail-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 40px;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--line);
        }}

        .detail-stats-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 20px;
            margin-bottom: 40px;
        }}

        .table-container {{
            background: linear-gradient(180deg, rgba(255, 251, 243, 0.94), rgba(250, 241, 229, 0.82));
            border-radius: var(--radius);
            box-shadow: var(--shadow);
            overflow: hidden;
            border: 1px solid rgba(120, 89, 53, 0.12);
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 0.9rem;
        }}

        .audit-table {{
            margin-top: 20px;
            margin-bottom: 40px;
        }}

        th {{
            background: linear-gradient(180deg, rgba(163, 78, 37, 0.10), rgba(195, 146, 47, 0.06));
            color: var(--accent);
            text-transform: uppercase;
            font-size: 0.7rem;
            letter-spacing: 0.1em;
            padding: 16px 20px;
        }}

        td {{
            padding: 18px 20px;
            border-bottom: 1px solid var(--line);
        }}

        tr:last-child td {{ border-bottom: none; }}
        tr:hover td {{ background: rgba(163, 78, 37, 0.03); }}

        @media (max-width: 980px) {{
            header {{
                grid-template-columns: 1fr;
            }}

            h1 {{
                max-width: none;
            }}

            .grid {{
                grid-template-columns: repeat(2, 1fr);
            }}

            .main-content {{
                grid-template-columns: 1fr;
            }}

            .recent-activity-shell {{
                overflow-x: auto;
            }}

            .recent-activity-table {{
                min-width: 1120px;
            }}
        }}

        @media (max-width: 720px) {{
            .container {{
                padding-left: 14px;
                padding-right: 14px;
            }}

            header {{
                padding: 24px 18px;
            }}

            .grid {{
                grid-template-columns: 1fr;
            }}

            .nav-actions {{
                border-radius: 24px;
            }}
        }}
    </style>
</head>
<body id="body">
    <aside class="sidebar" id="sidebar">
        <div class="sidebar-toggle" onclick="toggleSidebar()">◀</div>
        <div class="sidebar-brand">
            <div class="brand-dot"></div>
            <div class="brand-text">Skill Dispatcher</div>
        </div>
        <nav>
            <ul class="nav-menu">
                <li class="nav-item active" onclick="setView('dashboard')" id="nav-dashboard">
                    <span class="nav-icon">📊</span>
                    <span>Overview</span>
                </li>
                <li class="nav-item" onclick="setView('wallboard')" id="nav-wallboard">
                    <span class="nav-icon">🧱</span>
                    <span>Wallboard</span>
                </li>
                <li class="nav-item" onclick="setView('staleness')" id="nav-staleness">
                    <span class="nav-icon">🕰️</span>
                    <span>Staleness Report</span>
                </li>
                <li class="nav-item" onclick="setView('token-cost')" id="nav-token-cost">
                    <span class="nav-icon">🪙</span>
                    <span>Token Cost Reports</span>
                </li>
                <li class="nav-item" onclick="setView('all-activity')" id="nav-all-activity">
                    <span class="nav-icon">👥</span>
                    <span>All Performers</span>
                </li>
                <li class="nav-item" onclick="setView('all-models')" id="nav-all-models">
                    <span class="nav-icon">🤖</span>
                    <span>All Models</span>
                </li>
                <li class="nav-item" onclick="setView('all-chains')" id="nav-all-chains">
                    <span class="nav-icon">🔗</span>
                    <span>Defined Chains</span>
                </li>
            </ul>
        </nav>
        
    </aside>

    <!-- Audit Dashboard View -->
    <div class="container" id="dashboard">
        <header>
            <div class="hero-copy">
                <div class="eyebrow">Telemetry command center</div>
                <h1>Skill Dispatcher Overview <span class="info-trigger" onclick="toggleHelp()">?</span></h1>
                <div class="hero-subcopy">A warmer, sharper operational surface for routing health, recent handoffs, and policy-aware telemetry across your skill ecosystem.</div>
                <div class="timestamp">
                    <span>Log consulted at {consulted_at}</span>
                    <span>Latest event in snapshot {latest_event_at}</span>
                </div>
            </div>
            <div class="view-controls">
                <div class="snapshot-banner" id="snapshot-banner" style="margin-top:0">
                    This dashboard is a static snapshot of the dispatch log. It refreshes the page every 30 seconds.
                </div>
            </div>
        </header>

        <section id="orchestration-help" class="info-box">
            <h3 style="margin-top:0">The Orchestration Principle: Single Handoff</h3>
            <p><strong>What it is:</strong> The strategy of routing a cohesive task to a single specialized skill rather than breaking it into atomic, repetitive steps. This is the architectural default for the Skill Dispatcher.</p>
            <p><strong>Example:</strong> If an agent needs to create 10 Epics and 30 User Stories, it asks the Dispatcher <em>once</em> for a "Backlog Generation" handoff. The specialist skill then handles the remaining 40 items internally.</p>
            <p><strong>Why it's Default:</strong></p>
            <ul>
                <li><strong>Efficiency:</strong> Minimizes unnecessary routing overhead and latency.</li>
                <li><strong>Context:</strong> Preserves the full task context within a single specialist's execution loop.</li>
                <li><strong>Audit Integrity:</strong> Keeps the logs clean and focused on high-level architectural decisions rather than mechanical noise.</li>
            </ul>
            <p><strong>Visibility note:</strong> recent activity shows explicit dispatcher telemetry only. If a handed-off specialist delegates further work internally, those child skills appear only when they are separately logged or declared in registry metadata via <code>dispatcher-downstream-skills</code>.</p>
        </section>

        <section class="grid">
            <div class="card stat-card collapsible" id="card-stats-calls">
                <div class="card-header-toggle" onclick="toggleCard('card-stats-calls')">
                    <span class="stat-label">Total Skill Calls</span>
                    <span class="card-toggle-icon">▾</span>
                </div>
                <div class="card-content">
                    <div class="stat-value">{total_calls}</div>
                    <div class="stat-foot">dispatch events</div>
                </div>
            </div>
            <div class="card stat-card collapsible" id="card-stats-decisions">
                <div class="card-header-toggle" onclick="toggleCard('card-stats-decisions')">
                    <span class="stat-label">Decision Calls (H/S/N)</span>
                    <span class="card-toggle-icon">▾</span>
                </div>
                <div class="card-content">
                    {decision_markup}
                    <div class="stat-foot">handoff / sequence / no match</div>
                </div>
            </div>
            <div class="card stat-card collapsible" id="card-stats-skills">
                <div class="card-header-toggle" onclick="toggleCard('card-stats-skills')">
                    <span class="stat-label">Unique Capabilities</span>
                    <span class="card-toggle-icon">▾</span>
                </div>
                <div class="card-content">
                    <div class="stat-value">{unique_skills}</div>
                    <div class="stat-foot">skills observed</div>
                </div>
            </div>
            <div class="card stat-card collapsible" id="card-stats-policy">
                <div class="card-header-toggle" onclick="toggleCard('card-stats-policy')">
                    <span class="stat-label">Policy Lookups (H/M/E)</span>
                    <span class="card-toggle-icon">▾</span>
                </div>
                <div class="card-content">
                    {policy_markup}
                    <div class="stat-foot">hit / miss / error</div>
                </div>
            </div>
        </section>

        <section class="main-content">
            <div class="left-col">
                <div class="card collapsible" id="card-performers">
                    <div class="card-header-toggle" onclick="toggleCard('card-performers')">
                        <div class="section-kicker">Leaderboard</div>
                        <span class="card-toggle-icon">▾</span>
                    </div>
                    <div class="card-content">
                        <div class="section-heading-row">
                            <h2>Top Performers</h2>
                            <a href="?view=all-activity" class="all-link">(All)</a>
                        </div>
                        {leaderboard_html}
                    </div>
                </div>
                <div id="model-hits-host">
                    {model_hits_html}
                </div>
            </div>
                <div class="card collapsible" id="card-activity">
                    <div class="card-header-toggle" onclick="toggleCard('card-activity')">
                        <div class="section-kicker">Timeline</div>
                        <span class="card-toggle-icon">▾</span>
                    </div>
                    <div class="card-content">
                        <h2>Recent Activity</h2>
                        {timeline_html}
                    </div>
                </div>
                <div id="chains-host" style="grid-column: 1 / -1; width: 100%;">
                    {chains_html}
                </div>
            </section>
        </div>

        <!-- Wallboard View -->
        <div class="wall-shell" id="wallboard-view">
            <div class="wall-header">
                <h1>Live Skill Distribution</h1>
            </div>
            <div class="wall-grid-container" id="wallboard"></div>
        </div>

        <!-- All Activity View -->
        <div class="all-activity-shell" id="all-activity-view">
            <div class="shell-header">
                <div>
                    <span class="stat-label">Complete Leaderboard</span>
                    <h1>All Skills</h1>
                </div>
                <button class="btn btn-secondary" onclick="setView('dashboard')">Back to Dashboard</button>
            </div>
            <div class="card">
                {all_skills_html}
            </div>
        </div>

        <!-- All Models View -->
        <div class="all-models-shell" id="all-models-view">
            <div class="shell-header">
                <div>
                    <span class="stat-label">Model Distribution</span>
                    <h1>All Models</h1>
                </div>
                <button class="btn btn-secondary" onclick="setView('dashboard')">Back to Dashboard</button>
            </div>
            <div class="card">
                {all_models_html}
            </div>
        </div>

        <!-- Skill Detail View -->
        <div class="detail-shell" id="details">
            <div class="detail-header">
                <div>
                    <span class="stat-label">Agent Capability Detail</span>
                    <h1 id="detail-title">Skill Name</h1>
                </div>
            </div>
            
            <div class="detail-stats-grid" id="detail-stats"></div>
            
            <div class="card collapsible" id="card-skill-history">
                <div class="card-header-toggle" onclick="toggleCard('card-skill-history')">
                    <span class="stat-label">Invocation History</span>
                    <span class="card-toggle-icon">▾</span>
                </div>
                <div class="card-content">
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>Timestamp</th>
                                    <th>Model</th>
                                    <th>Intent</th>
                                    <th>Decision</th>
                                    <th>Policy</th>
                                    <th>Reasoning</th>
                                </tr>
                            </thead>
                            <tbody id="detail-table-body"></tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        <!-- All Defined Chains View -->
        <div class="all-chains-shell" id="all-chains-view">
            <div class="shell-header">
                <div>
                    <span class="stat-label">Chain Definitions</span>
                    <h1>All Defined Chains</h1>
                </div>
                <button class="btn btn-secondary" onclick="setView('dashboard')">Back to Dashboard</button>
            </div>
            <div class="card">
                <p style="color:#888;font-size:0.85rem;margin:0 0 24px">
                    Each card shows the full phase definition of a chain-capable skill.
                    Blue nodes are skill-handled phases; amber nodes are agent-handled.
                    Status colors (green/red) appear in the Orchestrator Chains section once a chain has been executed.
                </p>
                {all_chains_html}
            </div>
        </div>

        <!-- Staleness Report View -->
        <div class="staleness-shell" id="staleness-view">
            <div class="shell-header">
                <div>
                    <span class="stat-label">Harness Engineering Audit</span>
                    <h1>Staleness Report</h1>
                </div>
                <button class="btn btn-secondary" onclick="setView('dashboard')">Back to Dashboard</button>
            </div>

            <div style="width: 100%; max-width: 1200px; margin: 0 auto;">
                <div id="staleness-content">
                    {staleness_html}
                </div>
            </div>
        </div>

        <!-- Token Cost Reports View -->
        <div class="token-cost-shell" id="token-cost-view">
            <div class="shell-header">
                <div>
                    <span class="stat-label">Token Usage Cost Report</span>
                    <h1>Token Cost Reports</h1>
                </div>
                <button class="btn btn-secondary" onclick="setView('dashboard')">Back to Dashboard</button>
            </div>

            <div style="width: 100%;">
                <div id="token-cost-content">
                    {token_cost_html}
                </div>
            </div>
        </div>

    <script>
        const TREEMAP_DATA = {treemap_json};
        const ALL_EVENTS = {all_events_json};
        const SKILL_REGISTRY = {registry_json};
        const LOG_CONSULTED_AT = {json.dumps(consulted_at)};
        const SNAPSHOT_LATEST_EVENT_AT = {json.dumps(latest_event_at)};

        function formatAgeMinutes(totalMinutes) {{
            if (totalMinutes < 1) {{
                return 'under a minute';
            }}
            if (totalMinutes < 60) {{
                return `${{totalMinutes}} minute${{totalMinutes === 1 ? '' : 's'}}`;
            }}
            const hours = Math.floor(totalMinutes / 60);
            const minutes = totalMinutes % 60;
            if (minutes === 0) {{
                return `${{hours}} hour${{hours === 1 ? '' : 's'}}`;
            }}
            return `${{hours}}h ${{minutes}}m`;
        }}

        function updateSnapshotBanner() {{
            const banner = document.getElementById('snapshot-banner');
            if (!banner) {{
                return;
            }}
            const consultedAt = Date.parse(LOG_CONSULTED_AT);
            const latestEventAt = Date.parse(SNAPSHOT_LATEST_EVENT_AT);
            if (Number.isNaN(consultedAt)) {{
                return;
            }}

            const ageMinutes = Math.max(0, Math.floor((Date.now() - consultedAt) / 60000));
            const latestLagMinutes = Number.isNaN(latestEventAt)
                ? null
                : Math.max(0, Math.floor((consultedAt - latestEventAt) / 60000));
            const stale = ageMinutes >= 5;

            banner.classList.toggle('alert', stale);
            banner.innerHTML = stale
                ? `<strong>Snapshot age:</strong> ${{formatAgeMinutes(ageMinutes)}} old. This page is reloading, but the file itself has not been regenerated since the log was consulted.${{latestLagMinutes !== null ? ` The newest embedded event is ${{formatAgeMinutes(latestLagMinutes)}} older than that consult.` : ''}}`
                : `<strong>Snapshot age:</strong> ${{formatAgeMinutes(ageMinutes)}}. This dashboard is a static snapshot of the dispatch log and only changes when <code>wallboard.html</code> is regenerated.${{latestLagMinutes !== null ? ` The newest embedded event is ${{formatAgeMinutes(latestLagMinutes)}} older than the consult time.` : ''}}`;
        }}

        function setView(view, skill = null) {{
            const url = new URL(window.location);
            url.searchParams.set('view', view);
            if (skill) url.searchParams.set('skill', skill);
            else url.searchParams.delete('skill');
            window.history.replaceState({{}}, '', url);
            
            const body = document.getElementById('body');
            body.classList.remove('radiator-mode', 'detail-mode', 'all-activity-mode', 'all-models-mode', 'all-chains-mode', 'staleness-mode', 'token-cost-mode');

            // Update sidebar active state
            document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
            const activeNav = document.getElementById('nav-' + view);
            if (activeNav) activeNav.classList.add('active');

            if (view === 'wallboard') {{
                body.classList.add('radiator-mode');
                // Give the browser a moment to layout the shell before measuring for treemap
                requestAnimationFrame(() => {{
                    setTimeout(renderTreemap, 50);
                }});
            }} else if (view === 'detail') {{
                body.classList.add('detail-mode');
                renderDetail(skill);
            }} else if (view === 'all-activity') {{
                body.classList.add('all-activity-mode');
            }} else if (view === 'all-models') {{
                body.classList.add('all-models-mode');
            }} else if (view === 'all-chains') {{
                body.classList.add('all-chains-mode');
            }} else if (view === 'staleness') {{
                body.classList.add('staleness-mode');
            }} else if (view === 'token-cost') {{
                body.classList.add('token-cost-mode');
            }}
        }}

        function toggleCard(cardId) {{
            const card = document.getElementById(cardId);
            if (card) {{
                card.classList.toggle('collapsed');
                // Store state in localStorage
                const collapsed = card.classList.contains('collapsed');
                localStorage.setItem('card-' + cardId, collapsed ? 'collapsed' : 'expanded');
            }}
        }}

        function toggleSidebar() {{
            const sidebar = document.getElementById('sidebar');
            const body = document.getElementById('body');
            sidebar.classList.toggle('collapsed');
            body.classList.toggle('sidebar-collapsed');
            
            const isCollapsed = sidebar.classList.contains('collapsed');
            localStorage.setItem('sidebar-collapsed', isCollapsed ? 'true' : 'false');
            
            // Re-render treemap if active as width changed
            if (body.classList.contains('radiator-mode')) {{
                setTimeout(renderTreemap, 310); // Wait for transition
            }}
        }}

        function restoreCardStates() {{
            document.querySelectorAll('.collapsible').forEach(card => {{
                const state = localStorage.getItem('card-' + card.id);
                if (state === 'collapsed') {{
                    card.classList.add('collapsed');
                }} else if (state === 'expanded') {{
                    card.classList.remove('collapsed');
                }}
            }});

            const sidebarCollapsed = localStorage.getItem('sidebar-collapsed') === 'true';
            if (sidebarCollapsed) {{
                document.getElementById('sidebar').classList.add('collapsed');
                document.getElementById('body').classList.add('sidebar-collapsed');
            }}
        }}

        function toggleRadiator() {{
            const isWall = document.getElementById('body').classList.contains('radiator-mode');
            setView(isWall ? 'dashboard' : 'wallboard');
        }}

        function showDetail(skill) {{
            setView('detail', skill);
        }}

        function goHome() {{
            setView('dashboard');
        }}

        function toggleHelp() {{
            document.getElementById('orchestration-help').classList.toggle('active');
        }}

        function escapeHtml(value) {{
            return String(value).replace(/[&<>"']/g, char => ({{
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#39;'
            }}[char]));
        }}

        function modelNameForEvent(event) {{
            for (const key of ['model', 'model_name', 'llm_model', 'agent_model']) {{
                if (typeof event[key] === 'string' && event[key].trim()) {{
                    return event[key].trim();
                }}
            }}
            for (const key of ['model', 'model_info', 'llm']) {{
                const value = event[key];
                if (value && typeof value === 'object') {{
                    const nested = value.name || value.model || value.id;
                    if (typeof nested === 'string' && nested.trim()) {{
                        return nested.trim();
                    }}
                }}
            }}
            return 'Unknown model';
        }}

        function vendorForModel(modelName) {{
            const normalized = modelName.trim().toLowerCase();
            if (!normalized || normalized === 'unknown model') return ['unknown', '?'];
            if (normalized.startsWith('gpt-') || /^o[1345]/.test(normalized) || normalized.includes('codex')) return ['openai', 'OA'];
            if (normalized.startsWith('claude') || normalized.includes('anthropic')) return ['anthropic', 'A'];
            if (normalized.startsWith('gemini') || normalized.includes('google')) return ['google', 'G'];
            if (normalized.startsWith('llama') || normalized.startsWith('meta')) return ['meta', 'M'];
            if (normalized.startsWith('mistral') || normalized.startsWith('mixtral')) return ['mistral', 'Mi'];
            if (normalized.startsWith('grok') || normalized.includes('xai')) return ['xai', 'xAI'];
            if (normalized.startsWith('deepseek')) return ['deepseek', 'DS'];
            if (normalized.startsWith('command') || normalized.includes('cohere')) return ['cohere', 'Co'];
            return ['unknown', '?'];
        }}

        const SIMPLE_ICON_SLUGS = {{
            openai: 'openai',
            anthropic: 'anthropic',
            google: 'googlegemini',
            meta: 'meta',
            mistral: 'mistralai',
            xai: 'x',
            deepseek: 'deepseek',
            cohere: 'cohere'
        }};

        function simpleIconUrl(vendor) {{
            const slug = SIMPLE_ICON_SLUGS[vendor];
            return slug ? `https://cdn.jsdelivr.net/npm/simple-icons@v15/icons/${{slug}}.svg` : '';
        }}

        function renderModelBadge(event) {{
            const modelName = modelNameForEvent(event);
            const [vendor, logo] = vendorForModel(modelName);
            const safeModelName = escapeHtml(modelName);
            const safeVendor = escapeHtml(vendor);
            const safeLogo = escapeHtml(logo);
            const iconUrl = simpleIconUrl(vendor);
            const iconMarkup = iconUrl
                ? `<img class="vendor-icon" src="${{escapeHtml(iconUrl)}}" alt="${{safeVendor}}" onerror="this.style.display='none'; this.nextElementSibling.style.display='inline';">`
                : '';
            return `<span class="model-badge vendor-${{safeVendor}}" title="${{safeVendor}} model: ${{safeModelName}}">
                <span class="vendor-logo">${{iconMarkup}}<span class="vendor-fallback">${{safeLogo}}</span></span>
                <span class="model-name">${{safeModelName}}</span>
            </span>`;
        }}

        function renderDetail(skillName) {{
            // Filter events where the skillName is either the direct match or part of a sequence string
            const events = ALL_EVENTS.filter(e => {{
                const explicitSkills = Array.isArray(e.skills_used) ? e.skills_used : null;
                const parts = explicitSkills && explicitSkills.length
                    ? explicitSkills
                    : (e.selected_skill || "")
                        .replace(/[+]/g, ",")
                        .replace(/&/g, ",")
                        .split(",")
                        .map(p => p.strip ? p.strip() : p.trim());
                return parts.includes(skillName);
            }}).reverse();
            document.getElementById('detail-title').innerText = skillName;
            const skillMeta = SKILL_REGISTRY[skillName] || {{}};
            const downstreamSkills = Array.isArray(skillMeta.downstream_skills)
                ? skillMeta.downstream_skills
                : [];
            const downstreamLabel = downstreamSkills.length
                ? downstreamSkills.join(", ")
                : "No declared downstream skills";
            
            // Render Stats
            const lastSeen = events.length > 0 ? events[0].timestamp.split('T')[0] : 'Never';
            const intents = events.map(e => e.intent);
            const mostCommonIntent = intents.sort((a,b) =>
                intents.filter(v => v===a).length - intents.filter(v => v===b).length
            ).pop() || 'None';

            const statsGrid = document.getElementById('detail-stats');
            statsGrid.innerHTML = `
                <div class="card">
                    <span class="stat-label">Total Invocations</span>
                    <div class="stat-value">${{events.length}}</div>
                </div>
                <div class="card">
                    <span class="stat-label">Last Activity</span>
                    <div class="stat-value" style="font-size: 1.5rem; margin-top: 10px">${{lastSeen}}</div>
                </div>
                <div class="card" style="grid-column: span 2">
                    <span class="stat-label">Primary Mission</span>
                    <div class="stat-value" style="font-size: 1.2rem; margin-top: 12px; color: var(--muted)">${{mostCommonIntent}}</div>
                </div>
                <div class="card" style="grid-column: span 2">
                    <span class="stat-label">Policy Lookups</span>
                    <div class="stat-value" style="font-size: 1.5rem; margin-top: 10px">${{events.filter(e => e.policy_lookup).length}}</div>
                </div>
                <div class="card" style="grid-column: span 4">
                    <span class="stat-label">Declared Downstream Skills</span>
                    <div class="stat-value" style="font-size: 1.1rem; margin-top: 12px; color: var(--muted); line-height: 1.4">${{downstreamLabel}}</div>
                </div>
            `;

            // Render Table
            const tbody = document.getElementById('detail-table-body');
            tbody.innerHTML = events.map(e => `
                <tr>
                    <td style="color: var(--muted); font-family: monospace; font-size: 0.8rem">${{e.timestamp.replace('T', ' ').split('.')[0]}}</td>
                    <td>${{renderModelBadge(e)}}</td>
                    <td style="font-weight: 700">${{e.intent}}</td>
                    <td><span style="font-size: 0.7rem; padding: 4px 8px; background: var(--accent-soft); color: var(--accent); border-radius: 4px; font-weight: 800">${{e.decision || 'HANDOFF'}}</span></td>
                    <td style="color: var(--muted); font-size: 0.85rem">${{e.policy_lookup ? `${{e.policy_lookup.status}} / ${{e.policy_lookup.source}} / ${{e.policy_lookup.hit_count || 0}}` : 'none'}}</td>
                    <td style="color: var(--muted); font-size: 0.85rem">${{e.reason || e.reasoning || ''}}</td>
                </tr>
            `).join('');
        }}

        function renderTreemap() {{
            const wall = document.getElementById('wallboard');
            wall.innerHTML = '';
            
            const data = TREEMAP_DATA.map(d => ({{ ...d }}));
            const total = data.reduce((acc, curr) => acc + curr.count, 0);
            if (total === 0) return;

            const width = wall.clientWidth;
            const height = wall.clientHeight;
            const totalArea = width * height;
            data.forEach(d => d.area = (d.count / total) * totalArea);

            function squarify(elements, row, w, h, x, y) {{
                if (elements.length === 0) {{
                    if (row.length > 0) layoutRow(row, w, h, x, y);
                    return;
                }}

                const next = elements[0];
                const newRow = [...row, next];
                
                if (worst(row, w, h) >= worst(newRow, w, h)) {{
                    squarify(elements.slice(1), newRow, w, h, x, y);
                }} else {{
                    const [nx, ny, nw, nh] = layoutRow(row, w, h, x, y);
                    squarify(elements, [], nw, nh, nx, ny);
                }}
            }}

            function worst(row, w, h) {{
                if (row.length === 0) return Infinity;
                const s = row.reduce((acc, d) => acc + d.area, 0);
                const side = Math.min(w, h);
                const minArea = Math.min(...row.map(d => d.area));
                const maxArea = Math.max(...row.map(d => d.area));
                return Math.max((side * side * maxArea) / (s * s), (s * s) / (side * side * minArea));
            }}

            function layoutRow(row, w, h, x, y) {{
                const s = row.reduce((acc, d) => acc + d.area, 0);
                const side = Math.min(w, h);
                const isVertical = w > h;
                const rowWidth = isVertical ? s / h : w;
                const rowHeight = isVertical ? h : s / w;

                let offset = 0;
                row.forEach((item) => {{
                    const tile = document.createElement('div');
                    tile.className = 'wall-tile';
                    
                    const iW = isVertical ? rowWidth : item.area / rowHeight;
                    const iH = isVertical ? item.area / rowWidth : rowHeight;
                    const tX = isVertical ? x : x + offset;
                    const tY = isVertical ? y + offset : y;

                    tile.style.left = tX + 'px';
                    tile.style.top = tY + 'px';
                    tile.style.width = iW + 'px';
                    tile.style.height = iH + 'px';

                    const hue = (20 + (TREEMAP_DATA.findIndex(d => d.name === item.name) * 15)) % 360;
                    const sat = 35 + (item.count / total) * 35;
                    const lgt = 96 - (item.count / total) * 12;
                    tile.style.background = `hsl(${{hue}}, ${{sat}}%, ${{lgt}}%)`;
                    tile.style.borderLeft = `4px solid hsl(${{hue}}, ${{sat + 15}}%, 45%)`;

                    const area = iW * iH;
                    
                    // Dynamic Font Scaling with f-string escape
                    let fs = Math.sqrt(area) / 12;
                    fs = Math.min(fs, iH / 2.2); 
                    fs = Math.min(fs, iW / (item.name.length * 0.55)); 
                    fs = Math.max(5, Math.min(42, fs)); 

                    const showContent = iH > 20 && iW > 25;
                    const showCount = iH > 45;

                    tile.innerHTML = showContent ? `
                        <div class="tile-title" style="font-size: ${{fs}}px">${{item.name}}</div>
                        ${{showCount ? `<div class="tile-count" style="font-size: ${{fs * 0.5}}px">${{item.count}} calls</div>` : ''}}
                    ` : '';
                    tile.onclick = () => showDetail(item.name);
                    tile.classList.add('clickable');
                    wall.appendChild(tile);
                    offset += isVertical ? iH : iW;
                }});

                return isVertical ? [x + rowWidth, y, w - rowWidth, h] : [x, y + rowHeight, w, h - rowHeight];
            }}

            // Use a small timeout to ensure layout has settled if visibility just changed
            setTimeout(() => {{
                const w = wall.clientWidth;
                const h = wall.clientHeight;
                if (w > 0 && h > 0) {{
                    squarify(data, [], w, h, 0, 0);
                }}
            }}, 0);
        }}

        window.addEventListener('resize', () => {{
            if (document.getElementById('body').classList.contains('radiator-mode')) {{
                renderTreemap();
            }}
        }});

        // Restore view from URL as early as possible so meta-refresh reloads
        // don't flash the default dashboard before snapping to the active sub-view.
        function restoreViewFromUrl() {{
            const params = new URLSearchParams(window.location.search);
            const view = params.get('view');
            const skill = params.get('skill');

            if (view === 'wallboard') {{
                setView('wallboard');
            }} else if (view === 'detail' && skill) {{
                setView('detail', skill);
            }} else if (view === 'all-activity') {{
                setView('all-activity');
            }} else if (view === 'all-models') {{
                setView('all-models');
            }} else if (view === 'all-chains') {{
                setView('all-chains');
            }} else if (view === 'staleness') {{
                setView('staleness');
            }} else if (view === 'token-cost') {{
                setView('token-cost');
            }}
            updateSnapshotBanner();
            document.documentElement.classList.add('view-ready');
        }}
        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', () => {{
                restoreViewFromUrl();
                restoreCardStates();
            }});
        }} else {{
            restoreViewFromUrl();
            restoreCardStates();
        }}
        // Safety net: ensure the page is never left hidden if something throws.
        setTimeout(() => document.documentElement.classList.add('view-ready'), 1500);

        // Intercept clicks to stay in the same window
        document.addEventListener('click', e => {{
            const link = e.target.closest('a');
            if (link && !link.target && link.href) {{
                const url = new URL(link.href);
                if (url.origin === window.location.origin && url.pathname === window.location.pathname) {{
                    e.preventDefault();
                    const view = url.searchParams.get('view');
                    const skill = url.searchParams.get('skill');
                    setView(view, skill);
                }}
            }}
        }});
        setInterval(updateSnapshotBanner, 30000);
    </script>
</body>
</html>"""

if __name__ == "__main__":
    main()
