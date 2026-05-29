# harness_round03_01_2

Round 03.01 candidate generated from `harness_round02_01_2` and the round3_1 localization/improvement reports.

## Design Summary

A failure-arbitration variant. It keeps the winner's single ReAct loop but makes repeated failed calls into a compact registry whose checker returns next-action constraints rather than broad advice.

## Module Change Map

| Module | Stage 1 Failure Addressed | Stage 2 Direction Followed | Key Implementation Choice | Preserved Winner Behavior |
|---|---|---|---|---|
| Planning | Repair-loop drift | Structured Planning-to-Action status packet | REPAIR_REGISTRY_PACKET records failed call classes and allowed repairs | Repair-ledger intent |
| Action | Low-value repeated failures | Bounded Repair Registry | repair_registry_check throttles repeated audits and forbids unavailable-tool suggestions | Single executor |
| Memory | Generic repair reminders | Sparse Risk-Aware Memory Cues | schema and repeat-failure cues selected by context | Procedural memory only |
| Builder | Metadata consistency | Builder/wiring preservation | round_03_01 identity with max_tool_calls_per_step=2 | Local provider wiring |

## Runtime Notes

- Candidate directory: `harness_round03_01_2`
- Planning system: `round03_01_repair_registry_planning`
- Action system: `round03_01_repair_registry_react`
- Memory system: `round03_01_repair_registry_memory`
- Status contract: `REPAIR_REGISTRY_PACKET`
- The harness keeps one environment-acting executor and does not hard-code benchmark answers, item IDs, entities, folder names, or observed routes.
- The checker is non-environmental; it reads the recent trajectory and returns compact next-action constraints only.
- Optional prompt files are included because this harness factory loads planning and action behavior from local `toolcalling_agent.yaml` files.
