# 🚦 Skill Dispatcher

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![AgentSkills Standard](https://img.shields.io/badge/AgentSkills-Standard-green.svg)](https://agentskills.io)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=flat&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/jovd83)

**Skill Dispatcher** is a high-performance routing and orchestration layer for AI Agent ecosystems. It dynamically discovers, classifies, and sequences specialized AgentSkills to ensure optimal task execution with minimal risk.

## 🚀 The Problem

As an agent's skill library grows, "Skill Overload" occurs:
-   **Ambiguity**: Multiple skills (e.g., `bash-executor`, `python-executor`) may overlap.
-   **Inefficiency**: Routing to a broad generalist when a specialist is available.
-   **Risk**: Accidentally invoking write-heavy skills during an analysis phase.

## ✨ The Solution

The **Skill Dispatcher** solves this by acting as a strategic traffic controller:
1.  **Dynamic Discovery**: Scans local and environment-defined directories for skills.
2.  **Zero-Dependency Parsing**: Robustly indexes skill metadata (frontmatter) using standard library logic.
3.  **Heuristic Routing**: Uses a configurable `DISPATCH_POLICY.md` to decide between `HANDOFF`, `SEQUENCE`, or `NO_MATCH`.
4.  **Handoff Payloads**: Generates precise instructions for the next skill in the chain.

## 📁 Repository Structure

```text
skill-dispatcher/
├── pyproject.toml         # Project metadata
├── LICENSE                # MIT License
├── CONTRIBUTING.md        # How to help
└── skills/
    └── skill-dispatcher/  # The core AgentSkill
        ├── SKILL.md       # High-level dispatcher instructions
        ├── scripts/
        │   └── build_registry.py  # Zero-dependency discovery logic
        ├── registry/
        │   ├── DISPATCH_POLICY.md # Human-readable routing heuristics
        │   └── SKILL_REGISTRY.md  # Auto-generated skill index
        └── examples/      # Recommended reasoning scenarios
```

## 🛠️ Getting Started

### Installation

You can install this skill locally or from a GitHub repository using the `npx skills add` tool.

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

## 🧠 Memory & Context

The dispatcher is designed to work with **Skill-Local Persistent Memory**. If a `memory/routing_history.md` or `memory/routing_stats.json` is present, the dispatcher will prioritize skills with higher historical success for specific intents.

## ⚖️ Dispatch Policies

Our policies prioritize **Specificity over Breadth** and **Security over Speed**. 
-   **HANDOFF**: Single specialist match.
-   **SEQUENCE**: Multi-phase workflow (e.g., Analysis -> Implementation).
-   **NO_MATCH**: Safe fallback when no specialized skill meets the quality bar.

For more details, see [DISPATCH_POLICY.md](skills/skill-dispatcher/registry/DISPATCH_POLICY.md).
