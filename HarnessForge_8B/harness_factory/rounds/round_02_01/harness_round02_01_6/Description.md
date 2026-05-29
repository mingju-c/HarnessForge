# harness_round02_01_6

Round 02.01 candidate evolved from `harness_round01_6`.

## Design Summary

Raw final-binding specialist. It strengthens the winner canonicalization behavior by making exact raw field copying the central contract for machine-graded short answers.

## Module Change Map

| Module | Repair Mechanism | Implementation Choice | Preserved Winner Behavior |
|---|---|---|---|
| Planning | Answer type contract | RAW_ANSWER_CONTRACT records requested type, decisive observation, raw field, and explicit transformation | Preserves single-executor round01_6 behavior |
| Action | Exact final gate | raw_answer_check audits support and format when finalization is risky | Preserves single-executor round01_6 behavior |
| Memory | Raw-copy reminders | Memory triggers on structured values and final_answer risk | Preserves single-executor round01_6 behavior |
| Builder | Round-compatible wiring | Local `PlanningClass` injection, project root, metadata, and tool reference binding | Factory contract from round01 winner |

## Runtime Notes

- Candidate directory: `harness_round02_01_6`
- Planning system: `round02_01_raw_answer_planning`
- Action system: `round02_01_raw_answer_react`
- Memory system: `round02_01_raw_answer_memory`
- The harness does not hard-code benchmark answers, entity IDs, folder names, people, or dataset-specific cases.
- Any checker tool is non-environmental and only reads the current trajectory.
- Budgeting is intentionally light; the main control is observation-grounded status, not a hard cap.
