# harness_round03_03_5

## Design Summary

A low-overhead exact-finalization variant. It keeps the winner closest in shape, but makes the last step explicit: answer type, decisive observation, raw field, allowed transformation, and exact output string.

## Module Change Map

- Planning repair: `round03_03_raw_commit_planning` validates the `RAW_ANSWER_COMMITTER` status packet and deterministically repairs executable-looking plans into pending rows.
- Action repair: `round03_03_raw_commit_react` keeps one executor, guarded tools, `raw_commit_check`, terminal gate `prompt/checker-only`, and sequential mutation mode `not forced`.
- Memory repair: `round03_03_raw_commit_memory` emits at most one procedural risk cue per in-trajectory request and stores no task facts, IDs, answers, or benchmark-specific lessons.
- Cross-module interface repair: planning rows, action summaries, checker output, and memory cues all use blockers, open rows, required next moves, and final readiness instead of broad advice.
- Builder/wiring repair: metadata is native to `round_03_03` while preserving `PlanningClass` injection, project-root setup, vector memory wiring, and tool-agent back binding.

## Generalization Notes

This harness targets general control failures: prompt-resistant planning contracts, observation-closed rows, schema repair, relation evidence closure, and raw final commitment. It avoids item IDs, entity-specific fixes, hard-coded answers, and benchmark-specific expected values.

## Focus

  - answer_type_slot
  - decisive_raw_field
  - allowed_transformation
  - minimal_final_answer
