# harness_round03_03_3

## Design Summary

A retrieval and ToolHop specialist without adding acting agents. It makes the plan expose typed evidence slots, intermediate variables, rejected distractors, and relation closure criteria, then requires final answers and downstream transformations to use only closed slots.

## Module Change Map

- Planning repair: `round03_03_evidence_slot_planning` validates the `EVIDENCE_SLOT_CLOSER` status packet and deterministically repairs executable-looking plans into pending rows.
- Action repair: `round03_03_evidence_slot_react` keeps one executor, guarded tools, `evidence_slot_check`, terminal gate `prompt/checker-only`, and sequential mutation mode `not forced`.
- Memory repair: `round03_03_evidence_slot_memory` emits at most one procedural risk cue per in-trajectory request and stores no task facts, IDs, answers, or benchmark-specific lessons.
- Cross-module interface repair: planning rows, action summaries, checker output, and memory cues all use blockers, open rows, required next moves, and final readiness instead of broad advice.
- Builder/wiring repair: metadata is native to `round_03_03` while preserving `PlanningClass` injection, project-root setup, vector memory wiring, and tool-agent back binding.

## Generalization Notes

This harness targets general control failures: prompt-resistant planning contracts, observation-closed rows, schema repair, relation evidence closure, and raw final commitment. It avoids item IDs, entity-specific fixes, hard-coded answers, and benchmark-specific expected values.

## Focus

  - typed_evidence_slots
  - relation_chain_closure
  - distractor_rejection
  - raw_slot_finalization
