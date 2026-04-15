#!/usr/bin/env python3
"""Skill Dispatch Wallboard - Generates a premium HTML/CSS dashboard for skill usage."""

import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter

def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def main():
    script_dir = Path(__file__).parent.parent
    log_path = script_dir / "logs" / "dispatch_events.jsonl"
    # SAFE ZONE Priority: survive 'npx skills add' updates
    persistent_base = Path.home() / ".agents" / "logs" / "skill-dispatcher"
    
    if ".agents" in str(script_dir.resolve()).lower():
        report_dir = persistent_base / "reports"
    else:
        report_dir = script_dir / "reports"
        
    report_path = report_dir / "wallboard.html"
    staleness_report_path = report_dir / "staleness_report.md"

    events = []
    
    # Safe Zone Discovery
    persistent_log_path = Path.home() / ".agents" / "logs" / "skill-dispatcher" / "dispatch_events.jsonl"
    local_log_path = script_dir / "logs" / "dispatch_events.jsonl"
    
    # Priority: 
    # 1. Force Safe Zone if in installed context
    # 2. Local path (for local development)
    # 3. Safe Zone fallback (for hybrid environments)
    
    if ".agents" in str(script_dir.resolve()).lower():
        actual_log_path = persistent_log_path
    elif local_log_path.exists():
        actual_log_path = local_log_path
    else:
        actual_log_path = persistent_log_path

    if not actual_log_path.exists():
        print(f"[!] No log found at {actual_log_path}. Run migration or log an event first.")
        return

    with open(actual_log_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                try:
                    events.append(json.loads(line))
                except Exception:
                    continue

    if not events:
        print("[!] Log is empty.")
        return

    # Analytics
    total_calls = len(events)
    
    # Explode sequences for accurate skill usage counts
    skills_counter = Counter()
    for ev in events:
        raw_skill = ev.get("selected_skill", "Unknown")
        # Split by common sequence delimiters
        parts = [p.strip() for p in raw_skill.replace("+", ",").replace("&", ",").split(",")]
        for p in parts:
            if p:
                skills_counter[p] += 1
                
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

    # Decision analytics
    decision_counter = Counter(ev.get("decision", "HANDOFF") for ev in events)
    decision_summary = {
        "H": decision_counter.get("HANDOFF", 0),
        "S": decision_counter.get("SEQUENCE", 0),
        "N": decision_counter.get("NO_MATCH", 0)
    }

    # HTML Generation
    html_content = render_html(
        total_calls=total_calls,
        most_used_name=most_used[0],
        most_used_count=most_used[1],
        unique_skills=unique_skills,
        decision_summary=decision_summary,
        recent_events=recent,
        skills_summary=skills_counter.most_common(10),
        generated_at=utc_now(),
        treemap_json=json.dumps(treemap_data),
        all_events_json=json.dumps(events),
        environment_info=environment_info,
        staleness_html=staleness_html
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

def render_html(total_calls, most_used_name, most_used_count, unique_skills, decision_summary, recent_events, skills_summary, generated_at, treemap_json, all_events_json, environment_info, staleness_html):
    leaderboard_html = "".join([
        f'<div class="rank-row"><span class="clickable" onclick="showDetail(\'{name}\')">{name}</span><strong>{count}</strong></div>'
        for name, count in skills_summary
    ])

    timeline_html = "".join([
        f'<div class="event-card"> \
            <div class="time">{ev["timestamp"].split("T")[0]}</div> \
            <div class="badge {ev.get("decision", "HANDOFF").lower()}">{ev.get("decision", "HANDOFF")[0]}</div> \
            <div class="skill clickable" onclick="showDetail(\'{ev["selected_skill"]}\')">{ev["selected_skill"]}</div> \
            <div class="intent" title="{ev.get("reason", "")}">{ev["intent"]}</div> \
          </div>'
        for ev in recent_events
    ])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="refresh" content="30">
    <title>Skill Dispatcher Wallboard & Radiator</title>
    <style>
        :root {{
            --bg: #f3ede2;
            --paper: #fffaf1;
            --ink: #171512;
            --muted: #6d655a;
            --line: rgba(76, 58, 37, 0.16);
            --accent: #aa4b22;
            --accent-soft: rgba(170, 75, 34, 0.10);
            --olive: #42563d;
            --gold: #c58b2a;
            --shadow: 0 12px 40px rgba(48, 31, 12, 0.08);
            --radius: 16px;
        }}

        * {{ box-sizing: border-box; }}
        body {{
            margin: 0;
            background-color: var(--bg);
            color: var(--ink);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.5;
            transition: background 0.3s ease;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 40px 20px;
            transition: opacity 0.3s ease;
        }}

        header {{
            margin-bottom: 40px;
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--line);
        }}

        h1 {{
            font-family: Georgia, serif;
            font-size: 2.5rem;
            margin: 0;
            letter-spacing: -0.02em;
        }}

        .timestamp {{
            color: var(--muted);
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}

        .view-controls {{
            display: flex;
            gap: 12px;
        }}

        .btn {{
            background: var(--paper);
            border: 1px solid var(--line);
            border-radius: 999px;
            padding: 8px 20px;
            font-weight: 700;
            font-size: 0.85rem;
            cursor: pointer;
            transition: all 0.2s ease;
            color: var(--ink);
            text-decoration: none;
        }}

        .btn:hover {{
            background: var(--accent);
            color: white;
            border-color: transparent;
            box-shadow: 0 4px 12px rgba(170, 75, 34, 0.2);
        }}

        /* Info Styles */
        .info-trigger {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 24px;
            height: 24px;
            background: var(--accent);
            color: white;
            border-radius: 50%;
            font-size: 14px;
            font-weight: bold;
            cursor: pointer;
            margin-left: 10px;
            vertical-align: middle;
            transition: transform 0.2s ease;
        }}

        .info-trigger:hover {{ transform: scale(1.1); font-size: 16px; }}

        .info-box {{
            display: none;
            background: #fff;
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 20px;
            margin-top: 15px;
            font-size: 0.9rem;
            line-height: 1.6;
            color: var(--ink);
            box-shadow: var(--shadow);
        }}

        .info-box.active {{ display: block; }}
        .info-box strong {{ color: var(--accent); }}

        .grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 24px;
            margin-bottom: 40px;
        }}

        .card {{
            background: var(--paper);
            border: 1px solid var(--line);
            border-radius: var(--radius);
            padding: 24px;
            box-shadow: var(--shadow);
            backdrop-filter: blur(10px);
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
            font-size: 3rem;
            font-weight: 800;
            line-height: 1;
            margin-top: 4px;
        }}

        .accent-text {{ color: var(--accent); }}

        .main-content {{
            display: grid;
            grid-template-columns: 1fr 2fr;
            gap: 24px;
        }}

        h2 {{
            font-family: Georgia, serif;
            font-size: 1.5rem;
            margin-top: 0;
            margin-bottom: 20px;
        }}

        .rank-row {{
            display: flex;
            justify-content: space-between;
            padding: 12px 0;
            border-bottom: 1px solid var(--line);
        }}

        .event-card {{
            background: var(--paper);
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 12px;
            display: grid;
            grid-template-columns: 100px 40px 180px 1fr;
            align-items: center;
            gap: 15px;
        }}

        .badge {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 24px;
            height: 24px;
            border-radius: 6px;
            font-size: 0.7rem;
            font-weight: 800;
            color: white;
        }}

        .badge.handoff {{ background: var(--olive); }}
        .badge.sequence {{ background: var(--gold); }}
        .badge.no_match {{ background: var(--muted); }}

        .time {{ color: var(--muted); font-size: 0.85rem; }}
        .skill {{ font-weight: 700; color: var(--accent); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
        .intent {{ font-size: 0.9rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}

        /* Radiator Mode Styles */
        .wall-shell {{
            display: none;
            position: fixed;
            inset: 0;
            background: var(--bg);
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
            background: var(--paper);
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
            font-family: Georgia, serif;
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

        .ticker {{
            height: 44px;
            background: var(--ink);
            color: var(--bg);
            display: flex;
            align-items: center;
            overflow: hidden;
            border-radius: 99px;
            margin-top: 20px;
            font-size: 0.95rem;
            font-weight: 600;
        }}

        .ticker-inner {{
            display: flex;
            padding-left: 100%;
            animation: ticker 40s linear infinite;
        }}

        @keyframes ticker {{
            0% {{ transform: translate3d(0, 0, 0); }}
            100% {{ transform: translate3d(-100%, 0, 0); }}
        }}

        .ticker-item {{
            white-space: nowrap;
            padding: 0 40px;
            border-right: 1px solid rgba(255,255,255,0.1);
        }}

        .clickable {{
            cursor: pointer;
            text-decoration: underline dotted;
            text-underline-offset: 4px;
        }}

        .clickable:hover {{
            color: var(--accent);
        }}

        /* Detail View Styles */
        .detail-shell {{
            display: none;
            position: fixed;
            inset: 0;
            background: var(--bg);
            z-index: 2000;
            padding: 40px;
            overflow-y: auto;
        }}

        /* Detail/Staleness View Styles */
        .detail-shell, .staleness-shell {{
            display: none;
            position: fixed;
            inset: 0;
            background: var(--bg);
            z-index: 2000;
            padding: 40px;
            overflow-y: auto;
        }}

        body.detail-mode .container, body.detail-mode .wall-shell {{ display: none; }}
        body.detail-mode .detail-shell {{ display: block; }}

        body.staleness-mode .container, body.staleness-mode .wall-shell {{ display: none; }}
        body.staleness-mode .staleness-shell {{ display: block; }}

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
            background: var(--paper);
            border-radius: var(--radius);
            box-shadow: var(--shadow);
            overflow: hidden;
            border: 1px solid var(--line);
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
            background: var(--accent-soft);
            color: var(--accent);
            text-transform: uppercase;
            font-size: 0.7rem;
            letter-spacing: 0.1em;
            padding: 16px 20px;
        }}

        td {{
            padding: 16px 20px;
            border-bottom: 1px solid var(--line);
        }}

        tr:last-child td {{ border-bottom: none; }}
        tr:hover td {{ background: rgba(0,0,0,0.01); }}
    </style>
</head>
<body id="body">
    <!-- Audit Dashboard View -->
    <div class="container" id="dashboard">
        <header>
            <div>
                <h1>Skill Dispatcher Overview <span class="info-trigger" onclick="toggleHelp()">?</span></h1>
                <div class="timestamp">Generated on {generated_at}</div>
            </div>
            <div class="view-controls">
                <a href="?view=wallboard" class="btn">Show Wallboard</a>
                <a href="?view=staleness" class="btn">Show staleness report</a>
                <div style="text-align: right; margin-left: 20px;">
                    <span class="stat-label">System Integrity</span>
                    <span style="color: var(--olive); font-weight: 700;">● ACTIVE</span>
                </div>
            </div>
        </header>

        <section id="orchestration-help" class="info-box">
            <h3 style="margin-top:0">The Orchestration Principle: Single Handoff</h3>
            <p><strong>What it is:</strong> The strategy of routing a cohesive task to a single specialized skill rather than breaking it into atomic, repetitive steps. This is the architectural default for the Skill Dispatcher.</p>
            
            <p><strong>Example:</strong> If an agent needs to create 10 Epics and 30 User Stories, it asks the Dispatcher <em>once</em> for a "Backlog Generation" handoff. The specialist skill then handles the remaining 40 items internally.</p>
            
            <p><strong>Why it's Default:</strong> 
            <ul>
                <li><strong>Efficiency:</strong> Minimizes unnecessary routing overhead and latency.</li>
                <li><strong>Context:</strong> Preserves the full task context within a single specialist's execution loop.</li>
                <li><strong>Audit Integrity:</strong> Keeps the logs clean and focused on high-level architectural decisions (1 log entry) rather than mechanical noise.</li>
            </ul>
            </p>
        </section>

        <section class="grid">
            <div class="card">
                <span class="stat-label">Total Skill Calls</span>
                <div class="stat-value">{total_calls}</div>
            </div>
            <div class="card">
                <span class="stat-label">Decision Calls (H/S/N)</span>
                <div class="stat-value"><span style="color:var(--olive)">{decision_summary['H']}</span>/<span style="color:var(--gold)">{decision_summary['S']}</span>/<span style="color:var(--muted)">{decision_summary['N']}</span></div>
            </div>
            <div class="card">
                <span class="stat-label">Unique Capabilities</span>
                <div class="stat-value">{unique_skills}</div>
            </div>
        </section>

        <section class="main-content">
            <div class="card">
                <h2>Top Performers</h2>
                {leaderboard_html}
                <div style="margin-top: 40px;">
                   <span class="stat-label">Environment</span>
                   <div style="font-weight: 700;">{environment_info}</div>
                </div>
            </div>
            <div class="card">
                <h2>Recent Activity</h2>
                {timeline_html}
            </div>
        </section>
    </div>

    <!-- Wallboard View -->
    <div class="wall-shell" id="wallboard-view">
        <div class="wall-header">
            <h1>Live Skill Distribution</h1>
            <button class="btn" onclick="goHome()">Back to Overview</button>
        </div>
        <div class="wall-grid-container" id="wallboard"></div>
    </div>

    <!-- Skill Detail View -->
    <div class="detail-shell" id="details">
        <div class="detail-header">
            <div>
                <span class="stat-label">Agent Capability Detail</span>
                <h1 id="detail-title">Skill Name</h1>
            </div>
            <button class="btn" onclick="goHome()">Back to Overview</button>
        </div>
        
        <div class="detail-stats-grid" id="detail-stats"></div>
        
        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th>Timestamp</th>
                        <th>Intent</th>
                        <th>Decision</th>
                        <th>Reasoning</th>
                    </tr>
                </thead>
                <tbody id="detail-table-body"></tbody>
            </table>
        </div>
    </div>

    <!-- Staleness Report View -->
    <div class="staleness-shell" id="staleness-view">
        <div class="detail-header">
            <div>
                <span class="stat-label">Harness Engineering Audit</span>
                <h1>Staleness Report</h1>
            </div>
            <button class="btn" onclick="goHome()">Back to Overview</button>
        </div>
        
        <div class="card" style="max-width: 900px; margin: 0 auto; padding: 40px;">
            <div id="staleness-content">
                {staleness_html}
            </div>
        </div>
    </div>

    <script>
        const TREEMAP_DATA = {treemap_json};
        const ALL_EVENTS = {all_events_json};

        function setView(view, skill = null) {{
            const url = new URL(window.location);
            url.searchParams.set('view', view);
            if (skill) url.searchParams.set('skill', skill);
            else url.searchParams.delete('skill');
            window.history.replaceState({{}}, '', url);
            
            document.getElementById('body').classList.remove('radiator-mode', 'detail-mode', 'staleness-mode');
            
            if (view === 'wallboard') {{
                document.getElementById('body').classList.add('radiator-mode');
                renderTreemap();
            }} else if (view === 'detail') {{
                document.getElementById('body').classList.add('detail-mode');
                renderDetail(skill);
            }} else if (view === 'staleness') {{
                document.getElementById('body').classList.add('staleness-mode');
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

        function renderDetail(skillName) {{
            // Filter events where the skillName is either the direct match or part of a sequence string
            const events = ALL_EVENTS.filter(e => {{
                const s = e.selected_skill || "";
                const parts = s.replace(/[+]/g, ",").replace(/&/g, ",").split(",").map(p => p.strip ? p.strip() : p.trim());
                return parts.includes(skillName);
            }}).reverse();
            document.getElementById('detail-title').innerText = skillName;
            
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
            `;

            // Render Table
            const tbody = document.getElementById('detail-table-body');
            tbody.innerHTML = events.map(e => `
                <tr>
                    <td style="color: var(--muted); font-family: monospace; font-size: 0.8rem">${{e.timestamp.replace('T', ' ').split('.')[0]}}</td>
                    <td style="font-weight: 700">${{e.intent}}</td>
                    <td><span style="font-size: 0.7rem; padding: 4px 8px; background: var(--accent-soft); color: var(--accent); border-radius: 4px; font-weight: 800">${{e.decision || 'HANDOFF'}}</span></td>
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

            squarify(data, [], width, height, 0, 0);
        }}

        window.addEventListener('resize', () => {{
            if (document.getElementById('body').classList.contains('radiator-mode')) {{
                renderTreemap();
            }}
        }});

        // Handle URL parameters for direct deep-linking
        window.addEventListener('load', () => {{
            const params = new URLSearchParams(window.location.search);
            const view = params.get('view');
            const skill = params.get('skill');
            
            if (view === 'wallboard') {{
                setView('wallboard');
            }} else if (view === 'detail' && skill) {{
                setView('detail', skill);
            }} else if (view === 'staleness') {{
                setView('staleness');
            }}
        }});

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
    </script>
</body>
</html>"""

if __name__ == "__main__":
    main()
