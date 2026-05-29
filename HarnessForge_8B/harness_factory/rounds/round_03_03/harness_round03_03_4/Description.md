# harness_round03_03_4

## Design Summary

A stricter stateful-workflow variant. It routes non-read-only schemas to one mutation per step, maintains read-after-write postcondition rows, and uses a code-level completion gate for risky terminal calls after failed observations.

## Module Change Map

- Planning repair: `round03_03_postcondition_planning` validates the `POSTCONDITION_SENTINEL` status packet and deterministically repairs executable-looking plans into pending rows.
- Action repair: `round03_03_postcondition_react` keeps one executor, guarded tools, `postcondition_check`, terminal gate `enabled`, and sequential mutation mode `enabled for non-read-only schemas`.
- Memory repair: `round03_03_postcondition_memory` emits at most one procedural risk cue per in-trajectory request and stores no task facts, IDs, answers, or benchmark-specific lessons.
- Cross-module interface repair: planning rows, action summaries, checker output, and memory cues all use blockers, open rows, required next moves, and final readiness instead of broad advice.
- Builder/wiring repair: metadata is native to `round_03_03` while preserving `PlanningClass` injection, project-root setup, vector memory wiring, and tool-agent back binding.

## Generalization Notes

This harness targets general control failures: prompt-resistant planning contracts, observation-closed rows, schema repair, relation evidence closure, and raw final commitment. It avoids item IDs, entity-specific fixes, hard-coded answers, and benchmark-specific expected values.

## Focus

  - sequential_mutations
  - read_after_write_postconditions
  - complete_task_readiness
  - stateful_blocker_rows
