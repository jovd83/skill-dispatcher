# Reasoning Example: Skill Dispatcher

This example demonstrates how the `skill-dispatcher` should approach a complex user request by applying the heuristics in `DISPATCH_POLICY.md`.

## User Request

> "I need to evaluate the security of our custom login component in the `src/auth` folder. If there are vulnerabilities, please draft a plan to fix them using standard React security practices."

---

## Internal Chain of Thought

### 1. Intent Classification
- **Primary Intent**: Security Analysis (Scanning code for vulnerabilities).
- **Secondary Intent**: Implementation Planning (Drafting a fix/remediation plan).
- **Phase**: Analysis & Planning.

### 2. Registry Scan
- `semgrep-skill`: Expert at scanning code for vulnerabilities. (Match: Yes)
- `react-component-tester`: Good for functional testing, but security is secondary. (Match: Partial)
- `security-fixer`: Good for fixing bugs, but needs a report first. (Match: Partial)

### 3. Policy Application
- **Heuristic: Specificity**: `semgrep-skill` is the most specific for the primary intent (security analysis).
- **Heuristic: Logical Sequencing**: This is a two-phase task. The fix plan depends entirely on the results of the scan. Therefore, `SEQUENCE` is the optimal decision.
- **Risk Assessment**: `semgrep-skill` is read-only (`low` risk), which is safe for the analysis phase.

### 4. Conflict Resolution
- Between `semgrep-skill` and `react-component-tester`, `semgrep` takes precedence based on the **Tool Availability** heuristic if `semgrep` is in the registry tags.

---

## Optimal Output

```text
Decision: SEQUENCE

Primary skill: semgrep-skill
Secondary skill: react-authoring-skill

Architectural Reasoning:
- [Intent] User requires a two-phase security workflow: (1) Vulnerability discovery, and (2) Remediation planning.
- [Mapping] 'semgrep-skill' is mapped as the primary specialist for deep static analysis of the auth component. 'react-authoring-skill' is selected for the secondary phase to draft standards-compliant fixes.
- [Risk] Both skills are safe for this context; initial phase is read-only.

Handoff Payload:
- Intent: Perform a static security analysis of React components in src/auth to identify common vulnerabilities (XSS, Injection, etc.).
- Inputs: src/auth
- Constraints: Focus on standard OWASP Top 10 for web applications.
- Deliverable: A security audit report detailing findings and suggested remediations.
```
