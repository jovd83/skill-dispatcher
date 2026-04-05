# Manual Verification Checklist: Skill Dispatcher

Follow this checklist to verify the dispatcher's deployment and logic in a new environment.

## 1. Registry Generation
- [ ] Run `python skills/skill-dispatcher/scripts/build_registry.py`.
- [ ] Verify the script output shows `[SUCCESS]` or `[*]` messages.
- [ ] Check `skills/skill-dispatcher/registry/SKILL_REGISTRY.md`:
    - [ ] Does it contain all expected skills?
    - [ ] Are categories correctly assigned (e.g., `testing`, `analysis`)?
    - [ ] Are descriptions and tags accurate according to the source `SKILL.md` files?

## 2. Dispatch Logic Verification
Present these scenarios to the agent to test the dispatcher's reasoning:

### Scenario A: Specialist Handoff
- **Prompt**: "I need to run unit tests for my new Python script."
- **Expected Decision**: `HANDOFF`.
- **Expected Skill**: `pytest-skill` (or equivalent).
- **Verification**: Does the 'Why' section mention specificity?

### Scenario B: Logical Sequencing
- **Prompt**: "Analyze these complex legacy requirements and then write a test plan."
- **Expected Decision**: `SEQUENCE`.
- **Expected Skills**: `analysis-skill` -> `test-planner-skill`.
- **Verification**: Is the intent for Phase 1 clearly distinguished from Phase 2?

### Scenario C: Safe Fallback
- **Prompt**: "Write a poem about the color blue."
- **Expected Decision**: `NO_MATCH`.
- **Verification**: Does the dispatcher explain why (i.e., no creative writing skills in the registry)?

## 3. Environment Compatibility
- [ ] Verify `SKILL_DISPATCHER_EXTRA_DIRS` correctly includes skills from external paths.
- [ ] Test the script on both Windows (PowerShell) and POSIX (Bash/Zsh) environments if possible.

## 4. UI/DX Polish
- [ ] Check the root `README.md` for broken links.
- [ ] Ensure formatting remains consistent in the auto-generated registry.
