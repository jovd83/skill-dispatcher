# 🚦 Skill Dispatcher

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-2.2.0-orange.svg)](https://github.com/jovd83/skill-dispatcher)
[![AgentSkills Standard](https://img.shields.io/badge/AgentSkills-Standard-green.svg)](https://agentskills.io)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=flat&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/jovd83)

**Skill Dispatcher** is a high-performance routing and orchestration layer for AI Agent ecosystems. It utilizes a **Contract-Driven Routing** architecture to dynamically discover, classify, and sequence specialized AgentSkills, ensuring every task is handled by the most qualified capability.

## 🚀 The Problem

As an agent's skill library grows, "Skill Overload" occurs:
-   **Ambiguity**: Multiple skills (e.g., `bash-executor`, `python-executor`) may overlap.
-   **Inefficiency**: Routing to a broad generalist when a specialist is available.
-   **Risk**: Accidentally invoking write-heavy skills during an analysis phase.

## ✨ The Solution (v2.2)

The **Skill Dispatcher** solves this by acting as a strategic traffic controller:
1.  **Contract-Driven Routing**: Matches by `intent`, `artifact_type`, repo-native `stack`, and `risk` allowance rather than keyword guessing.
2.  **Dynamic Discovery**: Scans local (`./skills`), global (`~/.agents/skills`), and environment-defined (`SKILL_DISPATCH_EXTRA_DIRS`) directories.
3.  **Registry v2.0**: Robustly indexes skill metadata into machine-readable `SKILL_REGISTRY.json` for deterministic selection.
4.  **Workflow Orchestration**: Automatically decides between `HANDOFF`, `SEQUENCE` (multi-phase flow), or `NO_MATCH`.
5.  **Shared Memory Integration**: Promotes stable routing policies to a `shared-memory` skill for global consistency.

## 📋 Registry Contract v2.0

The dispatcher enforces a standardized interface for all skills in the ecosystem.

### Routing Inputs
- `intent`: Normalized goal (e.g., `design_confirmation_tests`).
- `current_artifact_type`: Artifact currently available (e.g., `repo_context`).
- `target_artifact_type`: Artifact expected from the next skill.
- `repo_context`: Stack evidence and repository conventions.
- `allowed_write_risk`: `low`, `medium`, or `high`.

### Dispatch Decisions
- **HANDOFF**: Single specialist match for a clear task.
- **SEQUENCE**: Multi-phase workflow (e.g., Analysis -> Implementation).
- **NO_MATCH**: Safe fallback with "Skill Gap" identification when no match meets the 80% quality bar.

## 📁 Repository Structure

```text
skill-dispatcher/
├── pyproject.toml         # Project metadata
├── LICENSE                # MIT License
├── CONTRIBUTING.md        # How to help
└── skills/
    └── skill-dispatcher/  # The core AgentSkill (Self-Contained)
        ├── SKILL.md       # v2.0 Contract definition & Instructions
        ├── scripts/
        │   ├── build_registry.py    # Discovery engine
        │   ├── dispatch_logger.py   # Event logger
        │   ├── generate_wallboard.py# Dashboard generator
        │   └── migrate_past_usage.py # History bootstrapper
        ├── registry/      # Routing source of truth
        ├── examples/      # Recommended scenarios
        ├── config/        # Local settings
        ├── logs/          # Usage history
        ├── reports/       # Visual dashboards
        ├── evals/         # Performance benchmarks
        └── tests/         # Quality assurance
```

## 🛠️ Getting Started

### Installation

You can install this skill locally or from a GitHub repository:

**Local Installation:**
```bash
npx skills add C:\projects\skills\Skill-dispatcher --skill skill-dispatcher
```

**GitHub Installation:**
```bash
npx skills add <username>/skill-dispatcher --skill skill-dispatcher
```

### Refreshing the Registry

Whenever you add or modify a skill in your ecosystem, refresh the registry:
```bash
cd skills/skill-dispatcher
python scripts/build_registry.py
```

## 🧠 Memory & Promotion

- **Local Memory**: Prioritizes skills based on repo-specific historical success.
- **Policy Promotion**: Identifies stable routing patterns and recommends promoting them to the `shared-memory` skill for use across your entire organization.

## 📊 Usage Monitoring

The Skill Dispatcher includes a built-in monitoring system to track skill usage frequency and rationale. It now includes robust wrappers to ensure it works correctly across different Python environments (including Windows).

### Usage (Manual)
If you need to manually log an event (e.g., when testing a specific skill routing):
```bash
# Windows
.\log-dispatch.cmd --skill <skill> --intent <intent> --reason <reason>

# Linux/macOS
./log-dispatch.sh --skill <skill> --intent <intent> --reason <reason>
```

### Feature Flag
You can toggle usage logging in `skills/skill-dispatcher/config/settings.json`:
```json
{
  "logging_enabled": true
}
```
*Note: Logging is enabled by default to provide audit evidence for AI Board reviews.*

### Skill Dispatcher Overview & Wallboard
To generate a human-readable dashboard and wallboard:
1. Ensure you have logs in `skills/skill-dispatcher/logs/dispatch_events.jsonl`.
2. Run the generator:
   ```bash
   cd skills/skill-dispatcher
   python scripts/generate_wallboard.py
   ```
3. Open `skills/skill-dispatcher/reports/wallboard.html` in your browser.

#### How it works

1. **Where does the info come from?**
The wallboard reads all its data from the `logs/dispatch_events.jsonl` file. This is a secure, local-only append-only log that stores every architectural decision.

2. **Is it auto-updated?**
**Yes!** We've implemented two layers of automation:
- **Auto-Generation**: Every time a skill is called (and logging is enabled), the `dispatch_logger.py` script automatically triggers the generator to update `reports/wallboard.html`.
- **Auto-Refresh**: The HTML file includes a 30-second "heartbeat".

### Bootstrapping History
If you are turning this on for the first time and want to capture past usage from your session logs, run the migration script:
```bash
cd skills/skill-dispatcher
python scripts/migrate_past_usage.py
```

## ⚖️ Core Policies

Our policies prioritize **Specificity over Breadth** and **Security over Speed**. 
-   **Specificity Rule**: Always prefer a niche specialist (e.g., `react-tester`) over a generalist.
-   **Risk Alignment**: Ensures skill write-access matches the current task phase.
-   **Stack Preference**: Favors repository-native tools over global defaults.

For more details, see [DISPATCH_POLICY.md](skills/skill-dispatcher/registry/DISPATCH_POLICY.md).
