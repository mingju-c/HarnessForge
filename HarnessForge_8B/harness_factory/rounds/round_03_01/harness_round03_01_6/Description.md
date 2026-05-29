# harness_round03_01_6

Round 03.01 candidate generated from `harness_round02_01_2` and the round3_1 localization/improvement reports.

## Design Summary

A routing variant that tries to avoid over-applying heavy checks. It classifies the active control route and uses only the gate needed for the current task shape.

## Module Change Map

| Module | Stage 1 Failure Addressed | Stage 2 Direction Followed | Key Implementation Choice | Preserved Winner Behavior |
|---|---|---|---|---|
| Planning | Verbose or drifting status | Structured Planning-to-Action Status Packet | ROUTED_STATUS_PACKET with active route | Compact planning |
| Action | Over/under-use of gates | Selective commit controls | route_risk_check plus soft terminal gate only for completion tools | Single executor |
| Memory | Memory noise | Sparse Risk-Aware Memory Cues | route and terminal cues | Procedural memory only |
| Builder | Factory compatibility | Builder/wiring preservation | local prompts and metadata | Tool reference binding |

## Runtime Notes

- Candidate directory: `harness_round03_01_6`
- Planning system: `round03_01_routed_status_planning`
- Action system: `round03_01_route_aware_react`
- Memory system: `round03_01_route_aware_memory`
- Status contract: `ROUTED_STATUS_PACKET`
- The harness keeps one environment-acting executor and does not hard-code benchmark answers, item IDs, entities, folder names, or observed routes.
- The checker is non-environmental; it reads the recent trajectory and returns compact next-action constraints only.
- Optional prompt files are included because this harness factory loads planning and action behavior from local `toolcalling_agent.yaml` files.
