# harness_round03_01_4

Round 03.01 candidate generated from `harness_round02_01_2` and the round3_1 localization/improvement reports.

## Design Summary

A retrieval-arbitration variant. It targets SearchQA-style distractors by requiring candidates to match the predicate and answer type before final_answer, while preserving direct search when evidence is decisive.

## Module Change Map

| Module | Stage 1 Failure Addressed | Stage 2 Direction Followed | Key Implementation Choice | Preserved Winner Behavior |
|---|---|---|---|---|
| Planning | SearchQA distractor selection | Typed Slot and Evidence Verification | EVIDENCE_PACKET names predicate, answer type, and distractor risk | Short compact plans |
| Action | Wrong entity extracted from useful search | Predicate and answer-type arbitration | predicate_evidence_check for ambiguous retrieval evidence | One executor and direct search |
| Memory | Raw-answer reminders too broad | Sparse Risk-Aware Memory Cues | distractor and raw-span cues | No answer storage |
| Builder | Provider consistency | Builder/wiring preservation | round_03_01 metadata and local prompts | Factory-compatible wiring |

## Runtime Notes

- Candidate directory: `harness_round03_01_4`
- Planning system: `round03_01_evidence_packet_planning`
- Action system: `round03_01_evidence_arbiter_react`
- Memory system: `round03_01_evidence_arbiter_memory`
- Status contract: `EVIDENCE_PACKET`
- The harness keeps one environment-acting executor and does not hard-code benchmark answers, item IDs, entities, folder names, or observed routes.
- The checker is non-environmental; it reads the recent trajectory and returns compact next-action constraints only.
- Optional prompt files are included because this harness factory loads planning and action behavior from local `toolcalling_agent.yaml` files.
