# harness_round03_01_8

Round 03.01 candidate generated from `harness_round02_01_2` and the round3_1 localization/improvement reports.

## Design Summary

A balanced hybrid variant. It folds the major Stage 2 directions into one compact packet and uses a throttled verifier only at irreversible boundaries, with a soft terminal gate for complete_task.

## Module Change Map

| Module | Stage 1 Failure Addressed | Stage 2 Direction Followed | Key Implementation Choice | Preserved Winner Behavior |
|---|---|---|---|---|
| Planning | Weak Planning -> Action handoff | Structured Planning-to-Action Status Packet | VERIFIED_STATUS_PACKET with obligations and verified rows/slots | Repair-ledger compactness |
| Action | Premature terminals, repair loops, wrong finalization | Stateful gate plus rare verifier | hybrid_status_verifier and soft terminal gate at boundaries | Single executor |
| Memory | Generic reminders | Sparse Risk-Aware Memory Cues | boundary-specific terminal/repair/slot/raw cues | No factual memory |
| Builder | Metadata consistency | Builder/wiring preservation | round_03_01 metadata and local provider injection | Factory contract |

## Runtime Notes

- Candidate directory: `harness_round03_01_8`
- Planning system: `round03_01_verified_status_planning`
- Action system: `round03_01_hybrid_verifier_react`
- Memory system: `round03_01_hybrid_verifier_memory`
- Status contract: `VERIFIED_STATUS_PACKET`
- The harness keeps one environment-acting executor and does not hard-code benchmark answers, item IDs, entities, folder names, or observed routes.
- The checker is non-environmental; it reads the recent trajectory and returns compact next-action constraints only.
- Optional prompt files are included because this harness factory loads planning and action behavior from local `toolcalling_agent.yaml` files.
