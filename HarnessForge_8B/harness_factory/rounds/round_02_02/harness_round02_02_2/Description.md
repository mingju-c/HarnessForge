# harness_round02_02_2

## Design Summary

A repair-first variant that keeps the direct executor but makes repeated failures explicit: every failed call is classified, blocked from blind repetition, and repaired through observed arguments or alternate schema-listed tools.

## Module Change Map

- Planning repair: `round02_02_repair_registry_planning` emits the `REPAIR_REGISTRY` contract with compact rows for obligations, bindings, blockers, and final readiness.
- Action repair: `round02_02_repair_registry_react` keeps the single executor and adds `repair_registry_check` as a rare non-environment checker plus guarded task tools under `round02_02_repair_registry`.
- Memory repair: `round02_02_repair_registry_memory` provides phase-aware procedural reminders for the candidate's focus without storing task facts, IDs, or answers.
- Builder/wiring repair: metadata is updated to `round_02_02`, preserves `PlanningClass` injection, selected-tool binding, project-root setup, and vector memory wiring.

## Generalization Notes

This harness does not contain benchmark-item IDs, entity names, hard-coded answers, or task-specific branches. Its behavior is expressed through schema grounding, observation-backed state, failure repair, evidence binding, and raw final copying, which are intended to transfer across EnvScaler, SearchQA, ToolHop, and unseen mixed tasks.

## Focus

  - error_class_repair
  - blocked_failed_call_registry
  - argument_provenance
