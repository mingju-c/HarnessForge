# harness_round03_01_5

Round 03.01 candidate generated from `harness_round02_01_2` and the round3_1 localization/improvement reports.

## Design Summary

A finalization-focused variant. It addresses near-correct but exact-wrong QA by making final answers pass a narrow raw-output commit checklist tied to the decisive observation.

## Module Change Map

| Module | Stage 1 Failure Addressed | Stage 2 Direction Followed | Key Implementation Choice | Preserved Winner Behavior |
|---|---|---|---|---|
| Planning | Final-answer contract drift | Raw Final-Answer Commit Preflight | RAW_ANSWER_PACKET with answer_type and raw_output fields | Compact one-hop plans |
| Action | Canonicalization and prose errors | Raw Final-Answer Commit Preflight | raw_answer_commit_check audits final form only at risk | Direct finalization when obvious |
| Memory | Weak canonicalization reminders | Sparse Risk-Aware Memory Cues | raw and transform cues | No factual memory |
| Builder | Metadata consistency | Builder/wiring preservation | round_03_01 metadata | Local provider wiring |

## Runtime Notes

- Candidate directory: `harness_round03_01_5`
- Planning system: `round03_01_raw_answer_packet_planning`
- Action system: `round03_01_raw_answer_react`
- Memory system: `round03_01_raw_answer_memory`
- Status contract: `RAW_ANSWER_PACKET`
- The harness keeps one environment-acting executor and does not hard-code benchmark answers, item IDs, entities, folder names, or observed routes.
- The checker is non-environmental; it reads the recent trajectory and returns compact next-action constraints only.
- Optional prompt files are included because this harness factory loads planning and action behavior from local `toolcalling_agent.yaml` files.
