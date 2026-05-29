# harness_round02_01_8

Round 02.01 candidate evolved from `harness_round01_6`.

## Design Summary

Compact hybrid candidate. It fuses ledger, slot, evidence, repair, and raw-answer controls but activates detail only when the task shape warrants it.

## Module Change Map

| Module | Repair Mechanism | Implementation Choice | Preserved Winner Behavior |
|---|---|---|---|
| Planning | Minimal status packet | COMPACT_STATUS_FUSION keeps pending/success/failure/slots-or-evidence/remaining/final criteria together | Preserves single-executor round01_6 behavior |
| Action | Risk-triggered controls | status_fusion_check is reserved for unresolved high-risk states rather than routine answers | Preserves single-executor round01_6 behavior |
| Memory | Sparse procedural cues | Memory uses a longer interval and focuses on the highest current risk | Preserves single-executor round01_6 behavior |
| Builder | Round-compatible wiring | Local `PlanningClass` injection, project root, metadata, and tool reference binding | Factory contract from round01 winner |

## Runtime Notes

- Candidate directory: `harness_round02_01_8`
- Planning system: `round02_01_compact_status_planning`
- Action system: `round02_01_compact_status_react`
- Memory system: `round02_01_compact_status_memory`
- The harness does not hard-code benchmark answers, entity IDs, folder names, people, or dataset-specific cases.
- Any checker tool is non-environmental and only reads the current trajectory.
- Budgeting is intentionally light; the main control is observation-grounded status, not a hard cap.
