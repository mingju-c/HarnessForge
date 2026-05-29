# harness_round03_04_2

## Design Summary

A schema-first direct harness. It preserves the winner's single executor and soft alias repair, but adds deterministic preflight for required keys, nested required fields, enums, and placeholder identifiers before the environment sees bad calls.

## Module Change Map

- Planning repair: `round03_04_schema_registry_planning` emits `SCHEMA_REPAIR_REGISTRY` rows for obligations, bindings, evidence slots, blockers, recovery state, answer type, and final readiness.
- Action repair: `round03_04_schema_registry_react` keeps one executor, wraps the winner guard with local schema preflight, adds `schema_repair_check` as a rare non-environment constraint checker, and keeps terminal calls observation-gated when enabled.
- Memory repair: `round03_04_schema_registry_memory` routes compact procedural reminders by failure class: schema repair, empty result, repeated failed call, verifier blocker, stateful postcondition, evidence binding, and raw final risk.
- Builder/wiring repair: metadata is updated to `round_03_04`, preserves `PlanningClass` injection, selected-tool binding, project-root setup, vector memory wiring, and local prompt loading.

## Generalization Notes

This harness stores no task facts, IDs, answers, trajectory-specific values, benchmark item IDs, or fixed recovery scripts. The mechanisms operate on tool schemas, observations, failure classes, relation support, and terminal readiness, so they are intended to transfer across stateful APIs, SearchQA-style retrieval, ToolHop-style dependent calls, and unseen mixed tasks.

## Focus

- hard_schema_preflight
- failed_call_registry
- changed_argument_retry
- terminal_schema_hygiene
