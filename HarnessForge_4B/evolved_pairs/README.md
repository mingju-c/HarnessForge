# Evolved Pairs (4B)

This folder contains the curated round-3 harness-policy pairs used for reproducible benchmark runs.

- `harness_factory/`: copied self-contained harness bundles selected from the full harness factory.
- `policy_factory/`: lightweight policy manifests. Large checkpoints are intentionally not committed.
- `pairs.yaml`: benchmark-to-harness-policy routing manifest.

## Pair Strengths

| Benchmark | Recommended Pair | What It Is Best For |
| --- | --- | --- |
| ToolHop | `01_harness5` | Best 4B ToolHop pair in the selected round-3 shortlist. It is useful when exact tool-chain recovery and final answer commitment matter more than raw speed. |
| HotpotQA | `03_harness3` | Strongest selected 4B HotpotQA pair. It is the preferred multi-hop QA option when evidence gathering and answer synthesis are the main bottlenecks. |
| 2WikiQA | `02_harness7` | Selected 4B 2WikiQA pair. It is useful for decomposed multi-hop questions where the agent must keep entities and bridge facts aligned. |
| TMDB | `01_harness5` | Best selected 4B TMDB pair. It is strongest on API-style endpoint planning, recovery from missing fields, and final response commitment. |
| API-Bank | `03_harness3` | Selected 4B API-Bank pair. It is intended for structured API-call workflows where argument discipline and stable finalization matter. |

## Pair Table

| Benchmark | Pair ID | Harness | Policy / Served Model |
| --- | --- | --- | --- |
| ToolHop | `01_harness5` | `rounds.round_03_01.harness_round03_01_5` | `qwen3-4B-round_03_01-harness5` |
| HotpotQA | `03_harness3` | `rounds.round_03_03.harness_round03_03_3` | `qwen3-4B-round_03_03-harness3` |
| 2WikiQA | `02_harness7` | `rounds.round_03_02.harness_round03_02_7` | `qwen3-4B-round_03_02-harness7` |
| TMDB | `01_harness5` | `rounds.round_03_01.harness_round03_01_5` | `qwen3-4B-round_03_01-harness5` |
| API-Bank | `03_harness3` | `rounds.round_03_03.harness_round03_03_3` | `qwen3-4B-round_03_03-harness3` |

Run a pair by passing `--harness_package evolved_pairs.harness_factory`, the harness module from the table, and the corresponding policy as `--model`.
