# harness_round02_02_4

## Design Summary

A stateful-workflow variant for EnvScaler-like tasks. It emphasizes sequential commit rows and terminal blockers, while preserving fast direct execution when the task is read-only.

## Module Change Map

- Planning repair: `round02_02_stateful_gate_planning` emits the `STATEFUL_GATE` contract with compact rows for obligations, bindings, blockers, and final readiness.
- Action repair: `round02_02_stateful_gate_react` keeps the single executor and adds `stateful_gate_check` as a rare non-environment checker plus guarded task tools under `round02_02_stateful_gate`.
- Memory repair: `round02_02_stateful_gate_memory` provides phase-aware procedural reminders for the candidate's focus without storing task facts, IDs, or answers.
- Builder/wiring repair: metadata is updated to `round_02_02`, preserves `PlanningClass` injection, selected-tool binding, project-root setup, and vector memory wiring.

## Generalization Notes

This harness does not contain benchmark-item IDs, entity names, hard-coded answers, or task-specific branches. Its behavior is expressed through schema grounding, observation-backed state, failure repair, evidence binding, and raw final copying, which are intended to transfer across EnvScaler, SearchQA, ToolHop, and unseen mixed tasks.

## Focus

  - envscaler_invariant_ledger
  - sequential_mutation_commit
  - terminal_blockers
