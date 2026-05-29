# harness_round02_01_2

Round 02.01 candidate evolved from `harness_round01_6`.

## Design Summary

Repair-first ledger executor. It keeps the winner single ReAct actor but makes repeated failures, bad IDs, missing entities, and precondition changes explicit before another retry.

## Module Change Map

| Module | Repair Mechanism | Implementation Choice | Preserved Winner Behavior |
|---|---|---|---|
| Planning | Repair ledger | REPAIR_LEDGER tracks pending rows, last failure, changed preconditions, and final criteria | Preserves single-executor round01_6 behavior |
| Action | Bounded failure triage | repair_triage_check classifies failure type and checks whether a retry actually changes something | Preserves single-executor round01_6 behavior |
| Memory | Error-phase reminders | BEGIN and IN reminders trigger on repeated failure, bad IDs, and stale placeholder risk | Preserves single-executor round01_6 behavior |
| Builder | Round-compatible wiring | Local `PlanningClass` injection, project root, metadata, and tool reference binding | Factory contract from round01 winner |

## Runtime Notes

- Candidate directory: `harness_round02_01_2`
- Planning system: `round02_01_repair_ledger_planning`
- Action system: `round02_01_repair_ledger_react`
- Memory system: `round02_01_repair_ledger_memory`
- The harness does not hard-code benchmark answers, entity IDs, folder names, people, or dataset-specific cases.
- Any checker tool is non-environmental and only reads the current trajectory.
- Budgeting is intentionally light; the main control is observation-grounded status, not a hard cap.
