# harness_round03_04_4

## Design Summary

A stateful-workflow specialist that remains general. It infers risk from tool schemas and names, keeps one environment actor, sequences mutations, and blocks completion after unresolved failed or unverified side-effect rows.

## Module Change Map

- Planning repair: `round03_04_postcondition_gate_planning` emits `STATEFUL_POSTCONDITION_GATE` rows for obligations, bindings, evidence slots, blockers, recovery state, answer type, and final readiness.
- Action repair: `round03_04_postcondition_gate_react` keeps one executor, wraps the winner guard with local schema preflight, adds `postcondition_gate_check` as a rare non-environment constraint checker, and keeps terminal calls observation-gated when enabled.
- Memory repair: `round03_04_postcondition_gate_memory` routes compact procedural reminders by failure class: schema repair, empty result, repeated failed call, verifier blocker, stateful postcondition, evidence binding, and raw final risk.
- Builder/wiring repair: metadata is updated to `round_03_04`, preserves `PlanningClass` injection, selected-tool binding, project-root setup, vector memory wiring, and local prompt loading.

## Generalization Notes

This harness stores no task facts, IDs, answers, trajectory-specific values, benchmark item IDs, or fixed recovery scripts. The mechanisms operate on tool schemas, observations, failure classes, relation support, and terminal readiness, so they are intended to transfer across stateful APIs, SearchQA-style retrieval, ToolHop-style dependent calls, and unseen mixed tasks.

## Focus

- stateful_side_effect_rows
- read_after_write_expectations
- sequential_mutations
- complete_task_gate
