"""
Staleness Audit Script
Analyzes dispatch_events.jsonl to identify underused skills.

Usage: python scripts/staleness_audit.py [--days 90] [--output reports/staleness_report.md]
"""
import json
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import Counter


def extract_logged_skills(event):
    """Return every skill represented by a log event."""
    skills_used = event.get("skills_used")
    if isinstance(skills_used, list):
        normalized = [skill.strip() for skill in skills_used if isinstance(skill, str) and skill.strip()]
        if normalized:
            return normalized

    legacy_skill = event.get("skill")
    if isinstance(legacy_skill, str) and legacy_skill.strip():
        return [legacy_skill.strip()]

    selected_skill = event.get("selected_skill", "")
    if isinstance(selected_skill, str) and selected_skill.strip():
        normalized = selected_skill.replace("+", ",").replace("&", ",")
        return [part.strip() for part in normalized.split(",") if part.strip()]

    return []


def load_events(log_path, cutoff_date):
    """Load dispatch events newer than cutoff_date."""
    events = []
    if not log_path.exists():
        return events
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            ts_raw = event.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_raw)
            except ValueError:
                ts = datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S")
                ts = ts.replace(tzinfo=timezone.utc)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= cutoff_date:
                events.append(event)
        except (json.JSONDecodeError, ValueError):
            continue
    return events


def load_registry(registry_path):
    """Load all skill names from the registry."""
    if not registry_path.exists():
        return []
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    return [s["name"] for s in data.get("skills", [])]


def generate_report(all_skills, usage_counts, days, cutoff_date):
    """Generate markdown staleness report."""
    total_invocations = sum(usage_counts.values())
    zero_usage = [s for s in all_skills if usage_counts.get(s, 0) == 0]
    low_usage = [s for s in all_skills if 0 < usage_counts.get(s, 0) <= 2]

    lines = [
        "# Harness Staleness Audit",
        "",
        f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Period**: Last {days} days (since {cutoff_date.strftime('%Y-%m-%d')})",
        f"**Total registered skills**: {len(all_skills)}",
        f"**Total invocations in period**: {total_invocations}",
        f"**Skills invoked in period**: {len(usage_counts)}",
        f"**Skills never invoked**: {len(zero_usage)}",
        f"**Skills with low usage (≤2)**: {len(low_usage)}",
        "",
        "---",
        "",
        "## Skills by Usage",
        "",
        "| Skill | Invocations | Recommendation |",
        "|-------|-------------|----------------|",
    ]

    for skill in sorted(all_skills):
        count = usage_counts.get(skill, 0)
        if count == 0:
            recommendation = "⚠️ SUNSET — zero usage, review for deprecation"
        elif count <= 2:
            recommendation = "🟡 MONITOR — low usage, verify still needed"
        else:
            recommendation = "✅ ACTIVE"
        lines.append(f"| `{skill}` | {count} | {recommendation} |")

    lines.extend([
        "",
        "## Top 10 Most Used Skills",
        "",
        "| Rank | Skill | Invocations |",
        "|------|-------|-------------|",
    ])
    for rank, (skill, count) in enumerate(usage_counts.most_common(10), 1):
        lines.append(f"| {rank} | `{skill}` | {count} |")

    lines.extend([
        "",
        "---",
        "",
        "## Recommended Actions",
        "",
        "1. **Review SUNSET skills** — are they compensating for model limitations that no longer exist?",
        "2. **Check for absorption** — has a broader skill absorbed the functionality?",
        "3. **Update lifecycle** — for confirmed sunsets, add to the SKILL.md frontmatter:",
        "   ```yaml",
        "   dispatcher-lifecycle: sunset",
        "   ```",
        "4. **Re-run registry build** — `python scripts/build_registry.py` to propagate changes",
        "5. **After 60 days in sunset with zero usage**, move to `archived`",
    ])

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Harness Staleness Audit")
    parser.add_argument("--days", type=int, default=90, help="Lookback period in days (default: 90)")
    parser.add_argument("--output", type=str, default=None, help="Output report path")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    root = script_dir.parent
    log_path = root / "logs" / "dispatch_events.jsonl"
    registry_path = root / "registry" / "SKILL_REGISTRY.json"

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    events = load_events(log_path, cutoff)
    all_skills = load_registry(registry_path)
    usage = Counter()
    for event in events:
        for skill in extract_logged_skills(event):
            usage[skill] += 1

    report = generate_report(all_skills, usage, args.days, cutoff)

    output_path = Path(args.output) if args.output else root / "reports" / "staleness_report.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"[*] Staleness report written to: {output_path}")
    print(f"[*] Period: last {args.days} days | {len(all_skills)} skills | {len(usage)} active | {len(all_skills) - len(usage)} unused")


if __name__ == "__main__":
    main()
