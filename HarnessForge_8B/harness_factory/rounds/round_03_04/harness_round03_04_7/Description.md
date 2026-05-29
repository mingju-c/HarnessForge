# harness_round03_04_7

## Design Summary

A recovery-oriented single executor. It targets low-value exploration by forcing empty results and failed calls into a compact failure class before retrying, broadening, switching tools, or declaring evidence-backed impossibility.

## Module Change Map

- Planning repair: `round03_04_recovery_packet_planning` emits `RECOVERY_STATUS_PACKET` rows for obligations, bindings, evidence slots, blockers, recovery state, answer type, and final readiness.
- Action repair: `round03_04_recovery_packet_react` keeps one executor, wraps the winner guard with local schema preflight, adds `recovery_packet_check` as a rare non-environment constraint checker, and keeps terminal calls observation-gated when enabled.
- Memory repair: `round03_04_recovery_packet_memory` routes compact procedural reminders by failure class: schema repair, empty result, repeated failed call, verifier blocker, stateful postcondition, evidence binding, and raw final risk.
- Builder/wiring repair: metadata is updated to `round_03_04`, preserves `PlanningClass` injection, selected-tool binding, project-root setup, vector memory wiring, and local prompt loading.

## Generalization Notes

This harness stores no task facts, IDs, answers, trajectory-specific values, benchmark item IDs, or fixed recovery scripts. The mechanisms operate on tool schemas, observations, failure classes, relation support, and terminal readiness, so they are intended to transfer across stateful APIs, SearchQA-style retrieval, ToolHop-style dependent calls, and unseen mixed tasks.

## Focus

- empty_result_classification
- bounded_recovery_moves
- failed_call_packet
- evidence_backed_impossibility
