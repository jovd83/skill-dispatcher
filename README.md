# Skill Dispatcher

[![Validate Skills](https://github.com/jovd83/skill-dispatcher/actions/workflows/validate.yml/badge.svg)](https://github.com/jovd83/skill-dispatcher/actions/workflows/validate.yml)
[![version](https://img.shields.io/badge/version-1.0.0-blue)](CHANGELOG.md)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=flat&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/jovd83)

High-performance routing engine for AI AgentSkills that classifies intent, scans available capabilities, and orchestrates optimal dispatch decisions.

## What This Skill Does

The `skill-dispatcher` acts as the strategic routing layer for your agent ecosystem. It ensures that every user request is handled by the most qualified specialized skill available, or an orchestrated sequence of skills, while minimizing risk and maximizing precision.

- **Intent Classification**: Rapidly identifies primary and secondary user goals.
- **Skill Discovery**: Dynamically indexes available capabilities from the local ecosystem.
- **Workflow Orchestration**: Determines if a task requires a single specialist or a multi-phase pipeline (`HANDOFF` vs `SEQUENCE`).
- **Conflict Resolution**: Chooses between overlapping skills based on specificity, risk, and historical performance.

## Core Competencies

- **Registry Management**: Automatically indexes skills into a structured `SKILL_REGISTRY.md`.
- **Heuristic Evaluation**: Applies policies to prefer narrow specialists over generalists.
- **State Alignment**: Matches skill requirements (like `writes_files`) with the current environment state.
- **Memory-Driven Routing**: Consults local history to refine future dispatch decisions.

## Design Principles

- **Precision Over Generality**: Prefer a narrow tool that does one thing perfectly.
- **Safety First**: Route to read-only or analytical skills before destructive ones if intent is ambiguous.
- **Zero Filler**: Provides structured routing packets without conversational overhead.
- **Minimal Sequence Depth**: Focuses on clear, shallow pipelines to maintain reliability.

## Repository Layout

```text
SKILL.md
README.md
registry/
|-- SKILL_REGISTRY.md    # Generated skill index
|-- DISPATCH_POLICY.md   # Routing heuristics
|-- README.md            # Internal architecture docs
`-- .ignore             # Exclusion rules
scripts/
`-- build_registry.py    # Registry generator
examples/
`-- reasoning_example.md  # Dispatch logic example
```

## Installation

Copy this folder into your agents' skills directory:

- project-local: `.agents/skills/skill-dispatcher/`
- user-local: `~/.agents/skills/skill-dispatcher/`

Ensure your host environment is configured to scan this directory for `SKILL.md`.

## Quick Start

The dispatcher is typically triggered when the primary agent receives a request that could benefit from specialized skills.

Example prompt triggers:
- `Which skill should I use to analyze this Python script?`
- `I need to run an accessibility audit and then fix the issues. Plan the flow.`
- `Review the available skills and tell me if any can handle PDF extraction.`

## Maintainers

Built and maintained by **jovd83**. Use the included scripts to keep your registry in sync with your local library.
