# harness_round02_02_6

## Design Summary

A schema-routing variant. It infers read-only versus mutable behavior from exposed tool schemas and keeps read-only evidence flexible while making mutable commits sequential and ledger-backed.

## Module Change Map

- Planning repair: `round02_02_schema_route_planning` emits the `SCHEMA_ROUTE` contract with compact rows for obligations, bindings, blockers, and final readiness.
- Action repair: `round02_02_schema_route_react` keeps the single executor and adds `schema_route_check` as a rare non-environment checker plus guarded task tools under `round02_02_schema_route`.
- Memory repair: `round02_02_schema_route_memory` provides phase-aware procedural reminders for the candidate's focus without storing task facts, IDs, or answers.
- Builder/wiring repair: metadata is updated to `round_02_02`, preserves `PlanningClass` injection, selected-tool binding, project-root setup, and vector memory wiring.

## Generalization Notes

This harness does not contain benchmark-item IDs, entity names, hard-coded answers, or task-specific branches. Its behavior is expressed through schema grounding, observation-backed state, failure repair, evidence binding, and raw final copying, which are intended to transfer across EnvScaler, SearchQA, ToolHop, and unseen mixed tasks.

## Focus

  - read_only_mutable_routing
  - sequential_writes
  - bounded_evidence_grouping
