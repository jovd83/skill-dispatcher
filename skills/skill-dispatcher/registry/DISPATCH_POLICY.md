# Dispatch Policy

The `skill-dispatcher` adheres to these core heuristics to ensure precision routing across complex multi-skill environments. These policies define the architectural guardrails for all dispatch decisions.

## 1. Capability-First Routing

Route by declared contract, not by hardcoded sibling references and not by lucky name matches.

Preferred evaluation order:

1. **Accepted Intent Match**: A skill that explicitly declares the requested `intent` wins over one that merely looks related.
2. **Capability Match**: If no exact intent match exists, prefer skills whose `capabilities` align with the requested step.
3. **Artifact Fit**: Prefer skills whose `input_artifacts` can consume the current artifact and whose `output_artifacts` can produce the requested target artifact.
4. **Category / Tag Fit**: Use category, tags, and description only after intent, capability, and artifact compatibility have been checked.

Prefer reading these fields from namespaced `metadata` keys such as `dispatcher-capabilities` and `dispatcher-accepted-intents`. Top-level routing fields are transitional only.

## 2. Hierarchy of Selection (Priority Tiers)

When multiple skills may apply, use this hierarchy to resolve conflicts:

1.  **Specificity (The Golden Rule)**: Always prefer a specialized skill (e.g., `react-hook-tester`) over a broad one (e.g., `web-tester`). Narrower skills possess more precise toolsets and better-defined context.
2.  **Risk Alignment**: Align the skill's `risk` profile with the current task phase. Do not use `high` risk implementation skills during an exploratory research phase.
3.  **Tool Availability**: If a skill uses a specific tool (e.g., `playwright`, `ripgrep`) that is pre-installed or requested, it takes precedence over general scripting skills.
4.  **Deterministic Directory Precedence**: If the same skill exists in multiple locations, keep the first skill discovered by the ordered registry scan. Local development paths outrank installed copies, and installed copies outrank extras only when discovered first by policy.

## 3. Universal Routing Contract

Every dispatcher request should be normalized to this packet before selection:

- `intent`
- `current_artifact_type`
- `target_artifact_type`
- `repo_context`
- `constraints`
- `preferred_stack`
- `allowed_write_risk`

Every dispatcher result should return:

- `decision`
- `selected_skill`
- `reason`
- `handoff_payload`

If a caller cannot provide all fields, the dispatcher may infer missing low-risk values from repo evidence, but it should keep assumptions explicit.

## 4. Intent-to-Category Mapping

Every request must be mapped to a core category to filter candidates:

-   **ANALYSIS**: Research, planning, requirement derivation, or auditing.
-   **IMPLEMENTATION**: Code generation, refactoring, documentation writing, or configuration editing.
-   **TESTING/QA**: Unit testing, E2E testing, security vulnerability scanning, or performance profiling.
-   **INFRASTRUCTURE**: Deployment, CI/CD configuration, environment setup, or CLI automation.

Use intent names that stay stable even if the concrete skillset changes. Examples:

- `design_confirmation_tests`
- `render_test_artifact`
- `implement_ui_confirmation_test`
- `generate_test_data`
- `review_automation_quality`

## 5. Repository-First Stack Selection

When the routing step depends on framework choice, prefer stack evidence in this order:

1. **Repository-native stack** inferred from manifests, configs, imports, or nearby tests
2. **Explicit user instruction**
3. **Shared-memory policy defaults**
4. **Organization-preferred fallback**

Example: if a repo already uses Cypress, do not route a UI confirmation test to Playwright just because Playwright is globally preferred.

## 6. Logical Sequence Heuristics

Only use the `SEQUENCE` decision if the task clearly benefits from a phased approach. Avoid "Sequence Bloat."

-   **Phase 1 (Input Preparation)**: If the task requires deep reading, requirement extraction, or dependency analysis before work can begin.
-   **Phase 1 (User Context)**: For any creative, architectural, or multi-step task, prefer routing to the `personal-context-portfolio` first to align with user preferences and constraints.
-   **Phase 2 (Specialist Execution)**: The primary task handler.
-   **Termination**: Sequences must have a clear exit point. Do not "recursive dispatch" unless the output of Phase 1 is a mandatory input for Phase 2.

## 7. Format & Deliverable Alignment

Match the **output format** requested by the user to the `category` and `tags` of the skill.
-   If the user wants a **Markdown Report**, prefer skills with a `reporting` tag.
-   If the user wants **Production Code**, ensure the skill has an `implementation` category and high reliability.
-   If the step expects a structured artifact, prefer a skill that explicitly declares the matching `output_artifacts`.

## 8. Metadata-Driven Decisions (No Keyword Guessing)

Do **NOT** pick a skill based on a lucky keyword match in the name. You must evaluate:
-   `accepted_intents`: Does the skill claim this exact routing intent?
-   `capabilities`: Does the skill solve this class of problem?
-   `input_artifacts` and `output_artifacts`: Is the handoff shape compatible?
-   `stack_tags`: Does the skill align with the required framework or toolchain?
-   `description`: Does it actually solve the *problem* defined by the user?
-   `tags`: Does its toolset align with the required tech stack?
-   `risk`: Is the user ready for the potential side effects of this skill?

## 9. Hardcoded-Path Fallback Policy

Direct sibling skill paths are allowed only as a temporary fallback when:

1. the registry has no qualifying match,
2. the caller has a vetted local path,
3. policy allows the fallback, and
4. the dispatcher records that this was a fallback rather than a registry-based match.

The target architecture is registry-driven routing. Hardcoded paths should shrink over time, not grow.

## 10. The NO_MATCH Principle

If no skill registry entry satisfies **at least 80%** of the user's requirements:
-   Return `NO_MATCH`.
-   Provide a brief architectural explanation of why no match was found.
-   Identify "Skill Gaps" (e.g., "The user needs a GraphQL tester, but only REST testers are available").

## 11. Shared Policy Alignment (Global Persistence)

If the `shared-memory` skill is active, routing should align with global organization-wide defaults:
- **Policy, not task state**: Shared memory should store stable cross-project routing policy, not repo-local or task-local routes.
- **Repo-first exception**: Repository-native evidence still outranks a generic global default unless shared policy explicitly requires otherwise for compliance.
- **SOPs**: Check for organization-wide Standard Operating Procedures that mandate a specific capability or sequence for compliance.
- **Promotion**: Identifying a new, stable routing policy is a high-value insight. Recommend its promotion to shared memory only when it is reusable across repositories.