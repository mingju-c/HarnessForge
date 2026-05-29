# harness_round03_04_8

## Design Summary

A dual-route generalist. It infers read-only versus stateful risk from exposed schemas and uses the same direct executor, routing status rows toward evidence slots for QA/ToolHop or mutation commit rows for EnvScaler-like workflows.

## Module Change Map

- Planning repair: `round03_04_dual_route_planning` emits `DUAL_ROUTE_LEDGER` rows for obligations, bindings, evidence slots, blockers, recovery state, answer type, and final readiness.
- Action repair: `round03_04_dual_route_react` keeps one executor, wraps the winner guard with local schema preflight, adds `dual_route_check` as a rare non-environment constraint checker, and keeps terminal calls observation-gated when enabled.
- Memory repair: `round03_04_dual_route_memory` routes compact procedural reminders by failure class: schema repair, empty result, repeated failed call, verifier blocker, stateful postcondition, evidence binding, and raw final risk.
- Builder/wiring repair: metadata is updated to `round_03_04`, preserves `PlanningClass` injection, selected-tool binding, project-root setup, vector memory wiring, and local prompt loading.

## Generalization Notes

This harness stores no task facts, IDs, answers, trajectory-specific values, benchmark item IDs, or fixed recovery scripts. The mechanisms operate on tool schemas, observations, failure classes, relation support, and terminal readiness, so they are intended to transfer across stateful APIs, SearchQA-style retrieval, ToolHop-style dependent calls, and unseen mixed tasks.

## Focus

- schema_inferred_routing
- read_only_evidence_slots
- stateful_commit_rows
- compact_shared_status
