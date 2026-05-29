# harness_round03_03_2

## Design Summary

A schema-first variant. It keeps direct execution, but the plan and action prompt emphasize exact tool names, required argument keys, ID/name provenance, failure classes, and a latch that prevents identical failed-call loops until a real precondition changes.

## Module Change Map

- Planning repair: `round03_03_schema_repair_planning` validates the `SCHEMA_REPAIR_LATCH` status packet and deterministically repairs executable-looking plans into pending rows.
- Action repair: `round03_03_schema_repair_react` keeps one executor, guarded tools, `schema_repair_check`, terminal gate `prompt/checker-only`, and sequential mutation mode `not forced`.
- Memory repair: `round03_03_schema_repair_memory` emits at most one procedural risk cue per in-trajectory request and stores no task facts, IDs, answers, or benchmark-specific lessons.
- Cross-module interface repair: planning rows, action summaries, checker output, and memory cues all use blockers, open rows, required next moves, and final readiness instead of broad advice.
- Builder/wiring repair: metadata is native to `round_03_03` while preserving `PlanningClass` injection, project-root setup, vector memory wiring, and tool-agent back binding.

## Generalization Notes

This harness targets general control failures: prompt-resistant planning contracts, observation-closed rows, schema repair, relation evidence closure, and raw final commitment. It avoids item IDs, entity-specific fixes, hard-coded answers, and benchmark-specific expected values.

## Focus

  - schema_preflight
  - failed_call_classes
  - blocked_identical_retries
  - argument_provenance
