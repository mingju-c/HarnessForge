# harness_round02_01_7

Round 02.01 candidate evolved from `harness_round01_6`.

## Design Summary

Recovery and terminal-contract specialist. It reduces empty actions, premature unavailable answers, and no-terminal endings while preserving the single executor.

## Module Change Map

| Module | Repair Mechanism | Implementation Choice | Preserved Winner Behavior |
|---|---|---|---|
| Planning | Recovery routes | RECOVERY_STATUS tracks failed route, changed strategy, remaining route, and terminal criteria | Preserves single-executor round01_6 behavior |
| Action | Non-empty terminal discipline | recovery_contract_check audits impossible or terminal claims only at risk points | Preserves single-executor round01_6 behavior |
| Memory | Stuck-state reminders | Memory triggers on errors, no-observation risk, and cannot-determine phrasing | Preserves single-executor round01_6 behavior |
| Builder | Round-compatible wiring | Local `PlanningClass` injection, project root, metadata, and tool reference binding | Factory contract from round01 winner |

## Runtime Notes

- Candidate directory: `harness_round02_01_7`
- Planning system: `round02_01_recovery_status_planning`
- Action system: `round02_01_recovery_status_react`
- Memory system: `round02_01_recovery_status_memory`
- The harness does not hard-code benchmark answers, entity IDs, folder names, people, or dataset-specific cases.
- Any checker tool is non-environmental and only reads the current trajectory.
- Budgeting is intentionally light; the main control is observation-grounded status, not a hard cap.
