# harness_round02_02_7

## Design Summary

A verifier-integration variant. It preserves the single executor but makes verifier use rare and contract-shaped: the checker must return a concrete next constraint and repeated checker calls are throttled.

## Module Change Map

- Planning repair: `round02_02_verifier_contract_planning` emits the `VERIFIER_CONTRACT` contract with compact rows for obligations, bindings, blockers, and final readiness.
- Action repair: `round02_02_verifier_contract_react` keeps the single executor and adds `verifier_contract_check` as a rare non-environment checker plus guarded task tools under `round02_02_verifier_contract`.
- Memory repair: `round02_02_verifier_contract_memory` provides phase-aware procedural reminders for the candidate's focus without storing task facts, IDs, or answers.
- Builder/wiring repair: metadata is updated to `round_02_02`, preserves `PlanningClass` injection, selected-tool binding, project-root setup, and vector memory wiring.

## Generalization Notes

This harness does not contain benchmark-item IDs, entity names, hard-coded answers, or task-specific branches. Its behavior is expressed through schema grounding, observation-backed state, failure repair, evidence binding, and raw final copying, which are intended to transfer across EnvScaler, SearchQA, ToolHop, and unseen mixed tasks.

## Focus

  - rare_action_binding_verifier
  - checker_loop_throttle
  - next_action_constraints
