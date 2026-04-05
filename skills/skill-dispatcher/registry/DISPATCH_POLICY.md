# Dispatch Policy

The `skill-dispatcher` adheres to these core heuristics to ensure precision routing across complex multi-skill environments. These policies define the architectural guardrails for all dispatch decisions.

## 1. Hierarchy of Selection (Priority Tiers)

When multiple skills may apply, use this hierarchy to resolve conflicts:

1.  **Specificity (The Golden Rule)**: Always prefer a specialized skill (e.g., `react-hook-tester`) over a broad one (e.g., `web-tester`). Narrower skills possess more precise toolsets and better-defined context.
2.  **Risk Alignment**: Align the skill's `risk` profile with the current task phase. Do not use `high` risk implementation skills during an exploratory research phase.
3.  **Tool Availability**: If a skill uses a specific tool (e.g., `playwright`, `ripgrep`) that is pre-installed or requested, it takes precedence over general scripting skills.

## 2. Intent-to-Category Mapping

Every request must be mapped to a core category to filter candidates:

-   **ANALYSIS**: Research, planning, requirement derivation, or auditing.
-   **IMPLEMENTATION**: Code generation, refactoring, documentation writing, or configuration editing.
-   **TESTING/QA**: Unit testing, E2E testing, security vulnerability scanning, or performance profiling.
-   **INFRASTRUCTURE**: Deployment, CI/CD configuration, environment setup, or CLI automation.

## 3. Logical Sequence Heuristics

Only use the `SEQUENCE` decision if the task clearly benefits from a phased approach. Avoid "Sequence Bloat."

-   **Phase 1 (Input Preparation)**: If the task requires deep reading, requirement extraction, or dependency analysis before work can begin.
-   **Phase 2 (Specialist Execution)**: The primary task handler.
-   **Termination**: Sequences must have a clear exit point. Do not "recursive dispatch" unless the output of Phase 1 is a mandatory input for Phase 2.

## 4. Format & Deliverable Alignment

Match the **output format** requested by the user to the `category` and `tags` of the skill.
-   If the user wants a **Markdown Report**, prefer skills with a `reporting` tag.
-   If the user wants **Production Code**, ensure the skill has an `implementation` category and high reliability.

## 5. Metadata-Driven Decisions (No Keyword Guessing)

Do **NOT** pick a skill based on a lucky keyword match in the name. You must evaluate:
-   `description`: Does it actually solve the *problem* defined by the user?
-   `tags`: Does its toolset align with the required tech stack?
-   `risk`: Is the user ready for the potential side effects of this skill?

## 6. The NO_MATCH Principle

If no skill registry entry satisfies **at least 80%** of the user's requirements:
-   Return `NO_MATCH`.
-   Provide a brief architectural explanation of why no match was found.
-   Identify "Skill Gaps" (e.g., "The user needs a GraphQL tester, but only REST testers are available").

## 7. Shared Policy Alignment (Global Persistence)

If the `shared-memory` skill is active, routing should align with global organization-wide defaults:
- **Overrides**: Global policies in shared memory take precedence over local heuristics.
- **SOPs**: Check for project-level "Standard Operating Procedures" that mandate a specific skill or sequence for compliance.
- **Promotion**: Identifying a new, stable routing pattern is a "high-value" insight. Recommend its promotion to shared memory to keep all agents synchronized.
