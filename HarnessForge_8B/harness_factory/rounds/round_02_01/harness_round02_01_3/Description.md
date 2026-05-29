# harness_round02_01_3

Round 02.01 candidate evolved from `harness_round01_6`.

## Design Summary

Retrieval-arbitration specialist. It preserves direct execution while adding explicit target, predicate, title, answer-type, and distractor checks before final_answer.

## Module Change Map

| Module | Repair Mechanism | Implementation Choice | Preserved Winner Behavior |
|---|---|---|---|
| Planning | Target-typed evidence chain | EVIDENCE_ARBITER records target/title, predicate, answer type, candidates, and rejected distractors | Preserves single-executor round01_6 behavior |
| Action | Candidate support check | evidence_arbitration_check is available only for ambiguous retrieval or near-match finalization | Preserves single-executor round01_6 behavior |
| Memory | Distractor-aware reminders | Memory reinforces query changes and raw supported output without storing facts | Preserves single-executor round01_6 behavior |
| Builder | Round-compatible wiring | Local `PlanningClass` injection, project root, metadata, and tool reference binding | Factory contract from round01 winner |

## Runtime Notes

- Candidate directory: `harness_round02_01_3`
- Planning system: `round02_01_evidence_arbitration_planning`
- Action system: `round02_01_evidence_arbitration_react`
- Memory system: `round02_01_evidence_arbitration_memory`
- The harness does not hard-code benchmark answers, entity IDs, folder names, people, or dataset-specific cases.
- Any checker tool is non-environmental and only reads the current trajectory.
- Budgeting is intentionally light; the main control is observation-grounded status, not a hard cap.
