# harness_round03_03_8

## Design Summary

A comprehensive but still single-executor candidate. It carries two compact ledgers: a state ledger for mutations and a relation ledger for evidence slots, with terminal gates routed to the ledger that matches the current risk.

## Module Change Map

- Planning repair: `round03_03_dual_ledger_planning` validates the `DUAL_LEDGER_HANDOFF` status packet and deterministically repairs executable-looking plans into pending rows.
- Action repair: `round03_03_dual_ledger_react` keeps one executor, guarded tools, `dual_ledger_check`, terminal gate `enabled`, and sequential mutation mode `enabled for non-read-only schemas`.
- Memory repair: `round03_03_dual_ledger_memory` emits at most one procedural risk cue per in-trajectory request and stores no task facts, IDs, answers, or benchmark-specific lessons.
- Cross-module interface repair: planning rows, action summaries, checker output, and memory cues all use blockers, open rows, required next moves, and final readiness instead of broad advice.
- Builder/wiring repair: metadata is native to `round_03_03` while preserving `PlanningClass` injection, project-root setup, vector memory wiring, and tool-agent back binding.

## Generalization Notes

This harness targets general control failures: prompt-resistant planning contracts, observation-closed rows, schema repair, relation evidence closure, and raw final commitment. It avoids item IDs, entity-specific fixes, hard-coded answers, and benchmark-specific expected values.

## Focus

  - state_ledger
  - relation_ledger
  - ledger_routed_terminal_gate
  - compact_cross_module_handoff
