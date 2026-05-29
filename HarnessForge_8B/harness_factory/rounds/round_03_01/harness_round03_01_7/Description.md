# harness_round03_01_7

Round 03.01 candidate generated from `harness_round02_01_2` and the round3_1 localization/improvement reports.

## Design Summary

A memory-centered variant that still keeps memory procedural. It routes at most one compact cue at a time, reducing prompt noise while nudging the right checklist for the current risk.

## Module Change Map

| Module | Stage 1 Failure Addressed | Stage 2 Direction Followed | Key Implementation Choice | Preserved Winner Behavior |
|---|---|---|---|---|
| Planning | Weak handoff to memory/action | Structured Planning-to-Action Status Packet | RISK_CUE_PACKET names the dominant current risk | Compact planning |
| Action | Checker/memory distraction | Sparse Risk-Aware Memory Cues | risk_cue_check used only when cue selection is unclear | Single executor |
| Memory | Broad reminders | Sparse Risk-Aware Memory Cues | prioritized rule list with max two memories | No task facts or answers stored |
| Builder | Metadata consistency | Builder/wiring preservation | round_03_01 metadata | Provider wiring |

## Runtime Notes

- Candidate directory: `harness_round03_01_7`
- Planning system: `round03_01_risk_cue_planning`
- Action system: `round03_01_risk_memory_react`
- Memory system: `round03_01_risk_routed_memory`
- Status contract: `RISK_CUE_PACKET`
- The harness keeps one environment-acting executor and does not hard-code benchmark answers, item IDs, entities, folder names, or observed routes.
- The checker is non-environmental; it reads the recent trajectory and returns compact next-action constraints only.
- Optional prompt files are included because this harness factory loads planning and action behavior from local `toolcalling_agent.yaml` files.
