# harness_round03_04_5

## Design Summary

A verifier-contract repair of the winner. It keeps the rare checker idea but makes the output parseable and binding: blocker, required observation, allowed next action, final permission, and explicit evidence limits.

## Module Change Map

- Planning repair: `round03_04_verifier_blocks_planning` emits `VERIFIER_BLOCK_PROTOCOL` rows for obligations, bindings, evidence slots, blockers, recovery state, answer type, and final readiness.
- Action repair: `round03_04_verifier_blocks_react` keeps one executor, wraps the winner guard with local schema preflight, adds `verifier_block_check` as a rare non-environment constraint checker, and keeps terminal calls observation-gated when enabled.
- Memory repair: `round03_04_verifier_blocks_memory` routes compact procedural reminders by failure class: schema repair, empty result, repeated failed call, verifier blocker, stateful postcondition, evidence binding, and raw final risk.
- Builder/wiring repair: metadata is updated to `round_03_04`, preserves `PlanningClass` injection, selected-tool binding, project-root setup, vector memory wiring, and local prompt loading.

## Generalization Notes

This harness stores no task facts, IDs, answers, trajectory-specific values, benchmark item IDs, or fixed recovery scripts. The mechanisms operate on tool schemas, observations, failure classes, relation support, and terminal readiness, so they are intended to transfer across stateful APIs, SearchQA-style retrieval, ToolHop-style dependent calls, and unseen mixed tasks.

## Focus

- parseable_verifier_fields
- blocker_enforcement
- rare_checker_use
- no_checker_as_evidence
