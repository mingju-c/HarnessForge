# harness_round02_01_1

Round 02.01 candidate evolved from `harness_round01_6`.

## Design Summary

Balanced observed-ledger canonical executor. It keeps the winner single ReAct actor and adds a compact ledger/status contract, bounded failure repair reminders, optional readiness checking, and mandatory raw final-answer binding.

## Module Change Map

| Module | Repair Mechanism | Implementation Choice | Preserved Winner Behavior |
|---|---|---|---|
| Planning | Observation-grounded ledger | OBSERVED_LEDGER separates pending rows, observed success/failure, slots, remaining work, and final criteria | Preserves single-executor round01_6 behavior |
| Action | Ledger review plus raw final gate | ledger_readiness_check audits unresolved rows, repeated failures, and raw answer support only when ambiguous | Preserves single-executor round01_6 behavior |
| Memory | Phase-aware repair reminders | BEGIN and IN reminders trigger on failure, terminal risk, or raw-value availability without storing task facts | Preserves single-executor round01_6 behavior |
| Builder | Round-compatible wiring | Local `PlanningClass` injection, project root, metadata, and tool reference binding | Factory contract from round01 winner |

## Runtime Notes

- Candidate directory: `harness_round02_01_1`
- Planning system: `round02_01_observed_ledger_planning`
- Action system: `round02_01_observed_ledger_react`
- Memory system: `round02_01_observed_ledger_memory`
- The harness does not hard-code benchmark answers, entity IDs, folder names, people, or dataset-specific cases.
- Any checker tool is non-environmental and only reads the current trajectory.
- Budgeting is intentionally light; the main control is observation-grounded status, not a hard cap.
