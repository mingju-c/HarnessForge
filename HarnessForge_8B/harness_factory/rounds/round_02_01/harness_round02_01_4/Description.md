# harness_round02_01_4

Round 02.01 candidate evolved from `harness_round01_6`.

## Design Summary

Typed slot-chain executor. It targets ToolHop-like failures by requiring observed prerequisite slots before relation traversal, extraction, arithmetic, date, or string transformation.

## Module Change Map

| Module | Repair Mechanism | Implementation Choice | Preserved Winner Behavior |
|---|---|---|---|
| Planning | Typed slot chain | SLOT_CHAIN_LEDGER derives slots from the task and tracks prerequisites | Preserves single-executor round01_6 behavior |
| Action | Prerequisite-gated transformation | slot_chain_check audits missing or placeholder slots before downstream transformations | Preserves single-executor round01_6 behavior |
| Memory | Placeholder-safe reminders | Memory triggers on unresolved slots and raw/transformed value risk | Preserves single-executor round01_6 behavior |
| Builder | Round-compatible wiring | Local `PlanningClass` injection, project root, metadata, and tool reference binding | Factory contract from round01 winner |

## Runtime Notes

- Candidate directory: `harness_round02_01_4`
- Planning system: `round02_01_slot_chain_planning`
- Action system: `round02_01_slot_chain_react`
- Memory system: `round02_01_slot_chain_memory`
- The harness does not hard-code benchmark answers, entity IDs, folder names, people, or dataset-specific cases.
- Any checker tool is non-environmental and only reads the current trajectory.
- Budgeting is intentionally light; the main control is observation-grounded status, not a hard cap.
