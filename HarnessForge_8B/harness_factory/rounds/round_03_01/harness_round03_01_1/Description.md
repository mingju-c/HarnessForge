# harness_round03_01_1

Round 03.01 candidate generated from `harness_round02_01_2` and the round3_1 localization/improvement reports.

## Design Summary

A stateful-first evolution of the repair ledger. It keeps one ReAct executor but adds an explicit OBLIGATION_PACKET, a soft complete_task gate, and memory cues that keep mutation rows open until successful observations close them.

## Module Change Map

| Module | Stage 1 Failure Addressed | Stage 2 Direction Followed | Key Implementation Choice | Preserved Winner Behavior |
|---|---|---|---|---|
| Planning | Premature terminal completion | Structured Planning-to-Action status packet | OBLIGATION_PACKET with mutable_obligation rows and final criteria | Compact repair-ledger planning |
| Action | complete_task after partial state change | Stateful Commit Gate | terminal_readiness_check plus soft complete_task wrapper | Single executor and closed-set schemas |
| Memory | Broad advisory reminders | Sparse Risk-Aware Memory Cues | terminal and repair cues only when risk markers appear | No task facts persisted |
| Builder | Round metadata mismatch | Builder/wiring preservation | round_03_01 metadata and local PlanningClass injection | Factory-compatible ToolCallingAgent wiring |

## Runtime Notes

- Candidate directory: `harness_round03_01_1`
- Planning system: `round03_01_obligation_packet_planning`
- Action system: `round03_01_commit_gate_react`
- Memory system: `round03_01_commit_gate_memory`
- Status contract: `OBLIGATION_PACKET`
- The harness keeps one environment-acting executor and does not hard-code benchmark answers, item IDs, entities, folder names, or observed routes.
- The checker is non-environmental; it reads the recent trajectory and returns compact next-action constraints only.
- Optional prompt files are included because this harness factory loads planning and action behavior from local `toolcalling_agent.yaml` files.
