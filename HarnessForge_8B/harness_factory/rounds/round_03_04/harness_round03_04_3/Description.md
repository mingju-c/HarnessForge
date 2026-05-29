# harness_round03_04_3

## Design Summary

A read-only and multi-hop oriented variant. It keeps the same direct executor, but makes the planning-to-action handoff relation-specific, with evidence slots, intermediate bindings, distractor risk, and exact raw final form.

## Module Change Map

- Planning repair: `round03_04_relation_binder_planning` emits `RELATION_EVIDENCE_BINDING` rows for obligations, bindings, evidence slots, blockers, recovery state, answer type, and final readiness.
- Action repair: `round03_04_relation_binder_react` keeps one executor, wraps the winner guard with local schema preflight, adds `relation_evidence_check` as a rare non-environment constraint checker, and keeps terminal calls observation-gated when enabled.
- Memory repair: `round03_04_relation_binder_memory` routes compact procedural reminders by failure class: schema repair, empty result, repeated failed call, verifier blocker, stateful postcondition, evidence binding, and raw final risk.
- Builder/wiring repair: metadata is updated to `round_03_04`, preserves `PlanningClass` injection, selected-tool binding, project-root setup, vector memory wiring, and local prompt loading.

## Generalization Notes

This harness stores no task facts, IDs, answers, trajectory-specific values, benchmark item IDs, or fixed recovery scripts. The mechanisms operate on tool schemas, observations, failure classes, relation support, and terminal readiness, so they are intended to transfer across stateful APIs, SearchQA-style retrieval, ToolHop-style dependent calls, and unseen mixed tasks.

## Focus

- relation_specific_slots
- intermediate_variable_binding
- distractor_rejection
- raw_answer_span
