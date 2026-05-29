# harness_round02_02_3

## Design Summary

A retrieval and multi-hop focused variant. It keeps one executor but requires candidate answers and intermediate variables to be tied to source observations before finalization or dependent hops.

## Module Change Map

- Planning repair: `round02_02_evidence_binding_planning` emits the `EVIDENCE_BINDING` contract with compact rows for obligations, bindings, blockers, and final readiness.
- Action repair: `round02_02_evidence_binding_react` keeps the single executor and adds `evidence_binding_check` as a rare non-environment checker plus guarded task tools under `round02_02_evidence_binding`.
- Memory repair: `round02_02_evidence_binding_memory` provides phase-aware procedural reminders for the candidate's focus without storing task facts, IDs, or answers.
- Builder/wiring repair: metadata is updated to `round_02_02`, preserves `PlanningClass` injection, selected-tool binding, project-root setup, and vector memory wiring.

## Generalization Notes

This harness does not contain benchmark-item IDs, entity names, hard-coded answers, or task-specific branches. Its behavior is expressed through schema grounding, observation-backed state, failure repair, evidence binding, and raw final copying, which are intended to transfer across EnvScaler, SearchQA, ToolHop, and unseen mixed tasks.

## Focus

  - searchqa_candidate_arbitration
  - toolhop_binding_table
  - decisive_evidence_finalization
