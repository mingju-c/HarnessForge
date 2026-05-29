# harness_round03_01_3

Round 03.01 candidate generated from `harness_round02_01_2` and the round3_1 localization/improvement reports.

## Design Summary

A ToolHop-oriented but task-general variant. It activates typed slot rows only for dependent hops and transformations, reducing wrong-chain answers while keeping one-hop tasks light.

## Module Change Map

| Module | Stage 1 Failure Addressed | Stage 2 Direction Followed | Key Implementation Choice | Preserved Winner Behavior |
|---|---|---|---|---|
| Planning | Unverified intermediate slots | Typed Slot and Evidence Verification | SLOT_CHAIN_PACKET with closed_if conditions | Compact planning |
| Action | Downstream transforms on wrong entity | Typed Slot and Evidence Verification | slot_closure_check before risky transformations | Direct tool-chain execution |
| Memory | Weak slot reminders | Sparse Risk-Aware Memory Cues | slot and transformation risk cues | No factual memory |
| Builder | Provider compatibility | Builder/wiring preservation | same ToolCallingAgent wiring with local PlanningClass | Single executor |

## Runtime Notes

- Candidate directory: `harness_round03_01_3`
- Planning system: `round03_01_slot_chain_packet_planning`
- Action system: `round03_01_slot_closure_react`
- Memory system: `round03_01_slot_chain_memory`
- Status contract: `SLOT_CHAIN_PACKET`
- The harness keeps one environment-acting executor and does not hard-code benchmark answers, item IDs, entities, folder names, or observed routes.
- The checker is non-environmental; it reads the recent trajectory and returns compact next-action constraints only.
- Optional prompt files are included because this harness factory loads planning and action behavior from local `toolcalling_agent.yaml` files.
