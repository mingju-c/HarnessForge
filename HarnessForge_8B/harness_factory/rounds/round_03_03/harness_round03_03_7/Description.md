# harness_round03_03_7

## Design Summary

A conservative generalist. It activates detailed ledgers only when the schema or trajectory shows risk, otherwise it preserves the winner's direct ReAct path for one-hop SearchQA and clean ToolHop chains.

## Module Change Map

- Planning repair: `round03_03_risk_routed_planning` validates the `RISK_ROUTED_MINIMALIST` status packet and deterministically repairs executable-looking plans into pending rows.
- Action repair: `round03_03_risk_routed_react` keeps one executor, guarded tools, `risk_snapshot_check`, terminal gate `prompt/checker-only`, and sequential mutation mode `enabled for non-read-only schemas`.
- Memory repair: `round03_03_risk_routed_memory` emits at most one procedural risk cue per in-trajectory request and stores no task facts, IDs, answers, or benchmark-specific lessons.
- Cross-module interface repair: planning rows, action summaries, checker output, and memory cues all use blockers, open rows, required next moves, and final readiness instead of broad advice.
- Builder/wiring repair: metadata is native to `round_03_03` while preserving `PlanningClass` injection, project-root setup, vector memory wiring, and tool-agent back binding.

## Generalization Notes

This harness targets general control failures: prompt-resistant planning contracts, observation-closed rows, schema repair, relation evidence closure, and raw final commitment. It avoids item IDs, entity-specific fixes, hard-coded answers, and benchmark-specific expected values.

## Focus

  - risk_triggered_controls
  - fast_read_only_path
  - sparse_memory_cues
  - compact_snapshot_gate
