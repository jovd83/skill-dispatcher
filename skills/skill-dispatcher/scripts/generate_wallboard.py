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
    report_path = script_dir / "reports" / "wallboard.html"

    if not log_path.exists():
        print(f"[!] No log found at {log_path}. Run migration or log an event first.")
        return

    events = []
    with open(log_path, "r", encoding="utf-8") as f:
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
    skills_counter = Counter(ev["selected_skill"] for ev in events)
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

    # HTML Generation
    html_content = render_html(
        total_calls=total_calls,
        most_used_name=most_used[0],
        most_used_count=most_used[1],
        unique_skills=unique_skills,
        recent_events=recent,
        skills_summary=skills_counter.most_common(10),
        generated_at=utc_now(),
        treemap_json=json.dumps(treemap_data),
        environment_info=environment_info
    )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"[*] Integrated wallboard generated at: {report_path}")

def render_html(total_calls, most_used_name, most_used_count, unique_skills, recent_events, skills_summary, generated_at, treemap_json, environment_info):
    leaderboard_html = "".join([
        f'<div class="rank-row"><span>{name}</span><strong>{count}</strong></div>'
        for name, count in skills_summary
    ])

    timeline_html = "".join([
        f'<div class="event-card"> \
            <div class="time">{ev["timestamp"].split("T")[0]}</div> \
            <div class="skill">{ev["selected_skill"]}</div> \
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
            grid-template-columns: 120px 180px 1fr;
            align-items: center;
        }}

        .time {{ color: var(--muted); font-size: 0.85rem; }}
        .skill {{ font-weight: 700; color: var(--accent); }}
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
    </style>
</head>
<body id="body">
    <!-- Audit Dashboard View -->
    <div class="container" id="dashboard">
        <header>
            <div>
                <h1>Skill Dispatcher Overview</h1>
                <div class="timestamp">Generated on {generated_at}</div>
            </div>
            <div class="view-controls">
                <button class="btn" onclick="toggleRadiator()">Show Wallboard</button>
                <div style="text-align: right; margin-left: 20px;">
                    <span class="stat-label">System Integrity</span>
                    <span style="color: var(--olive); font-weight: 700;">● ACTIVE</span>
                </div>
            </div>
        </header>

        <section class="grid">
            <div class="card">
                <span class="stat-label">Total Skill Calls</span>
                <div class="stat-value">{total_calls}</div>
            </div>
            <div class="card">
                <span class="stat-label">Unique Capabilities</span>
                <div class="stat-value">{unique_skills}</div>
            </div>
            <div class="card">
                <span class="stat-label">Most Used Specialist</span>
                <div class="stat-value accent-text" style="font-size: 1.5rem; margin-top: 15px;">{most_used_name}</div>
                <div style="color: var(--muted); font-size: 0.8rem; margin-top: 4px;">{most_used_count} invocations</div>
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

    <!-- Radiator View -->
    <div class="wall-shell" id="radiator">
        <div class="wall-header">
            <h1 style="color: var(--ink)">Skill Dispatch Wallboard</h1>
            <button class="btn" onclick="toggleRadiator()">Return to overview</button>
        </div>
        <div class="wall-grid-container" id="wallboard"></div>
        <div class="ticker">
            <div class="ticker-inner">
                {"".join([f'<div class="ticker-item">Latest: {ev["selected_skill"]} for "{ev["intent"]}" &raquo; {ev.get("decision", "HANDOFF")}</div>' for ev in recent_events])}
            </div>
        </div>
    </div>

    <script>
        const TREEMAP_DATA = {treemap_json};

        function toggleRadiator() {{
            document.getElementById('body').classList.toggle('radiator-mode');
            if (document.getElementById('body').classList.contains('radiator-mode')) {{
                renderTreemap();
            }}
        }}

        function renderTreemap() {{
            const wall = document.getElementById('wallboard');
            wall.innerHTML = '';
            
            const total = TREEMAP_DATA.reduce((acc, curr) => acc + curr.count, 0);
            if (total === 0) return;

            const width = wall.clientWidth;
            const height = wall.clientHeight;
            
            let x = 0;
            let y = 0;
            let remainingWidth = width;
            let remainingHeight = height;
            let currentSum = total;

            TREEMAP_DATA.forEach((item, index) => {{
                const tile = document.createElement('div');
                tile.className = 'wall-tile';
                
                // The portion of the CURRENT remaining area this item should take
                const portion = item.count / currentSum;
                
                let tileWidth, tileHeight;
                
                if (remainingWidth > remainingHeight) {{
                    tileWidth = remainingWidth * portion;
                    if (index === TREEMAP_DATA.length - 1) tileWidth = remainingWidth;
                    tileHeight = remainingHeight;
                    tile.style.left = x + 'px';
                    tile.style.top = y + 'px';
                    tile.style.width = tileWidth + 'px';
                    tile.style.height = tileHeight + 'px';
                    x += tileWidth;
                    remainingWidth -= tileWidth;
                }} else {{
                    tileWidth = remainingWidth;
                    tileHeight = remainingHeight * portion;
                    if (index === TREEMAP_DATA.length - 1) tileHeight = remainingHeight;
                    tile.style.left = x + 'px';
                    tile.style.top = y + 'px';
                    tile.style.width = tileWidth + 'px';
                    tile.style.height = tileHeight + 'px';
                    y += tileHeight;
                    remainingHeight -= tileHeight;
                }}

                // Aesthetic enhancements
                const hue = 20 + (index * 15) % 360; 
                const saturation = 30 + (item.count / total) * 40;
                const lightness = 95 - (item.count / total) * 10;
                tile.style.background = `hsl(${{hue}}, ${{saturation}}%, ${{lightness}}%)`;
                tile.style.borderLeft = `4px solid hsl(${{hue}}, ${{saturation + 20}}%, 40%)`;

                const area = parseFloat(tile.style.width) * parseFloat(tile.style.height);
                const fontSize = Math.max(10, Math.min(42, Math.sqrt(area) / 10));
                
                tile.innerHTML = `
                    <div class="tile-title" style="font-size: ${{fontSize}}px">${{item.name}}</div>
                    <div class="tile-count" style="font-size: ${{fontSize * 0.4}}px">${{item.count}} calls</div>
                `;
                
                currentSum -= item.count;
                wall.appendChild(tile);
            }});
        }}

        window.addEventListener('resize', () => {{
            if (document.getElementById('body').classList.contains('radiator-mode')) {{
                renderTreemap();
            }}
        }});

        // Handle URL parameters for direct deep-linking to wallboard
        if (window.location.search.includes('view=wallboard')) {{
            toggleRadiator();
        }}
    </script>
</body>
</html>"""

if __name__ == "__main__":
    main()
