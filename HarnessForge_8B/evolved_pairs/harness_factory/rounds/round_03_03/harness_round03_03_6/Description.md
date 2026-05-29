# harness_round03_03_6

## Design Summary

A verifier-interface variant. It keeps a single acting executor, but any checker or memory cue must be converted into an explicit blocker, required next move, or finalization permission; checker text is never evidence.

## Module Change Map

- Planning repair: `round03_03_constraint_bridge_planning` validates the `CONSTRAINT_BRIDGE` status packet and deterministically repairs executable-looking plans into pending rows.
- Action repair: `round03_03_constraint_bridge_react` keeps one executor, guarded tools, `constraint_bridge_check`, terminal gate `prompt/checker-only`, and sequential mutation mode `not forced`.
- Memory repair: `round03_03_constraint_bridge_memory` emits at most one procedural risk cue per in-trajectory request and stores no task facts, IDs, answers, or benchmark-specific lessons.
- Cross-module interface repair: planning rows, action summaries, checker output, and memory cues all use blockers, open rows, required next moves, and final readiness instead of broad advice.
- Builder/wiring repair: metadata is native to `round_03_03` while preserving `PlanningClass` injection, project-root setup, vector memory wiring, and tool-agent back binding.

## Generalization Notes

This harness targets general control failures: prompt-resistant planning contracts, observation-closed rows, schema repair, relation evidence closure, and raw final commitment. It avoids item IDs, entity-specific fixes, hard-coded answers, and benchmark-specific expected values.

## Focus

  - structured_checker_constraints
  - memory_to_action_blockers
  - checker_loop_throttle
  - evidence_not_advice
