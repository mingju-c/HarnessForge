# Evolved Pairs (8B)

This folder contains the curated round-3 harness-policy pairs used for reproducible benchmark runs.

- `harness_factory/`: copied self-contained harness bundles selected from the full harness factory.
- `policy_factory/`: lightweight policy manifests. Large checkpoints are intentionally not committed.
- `pairs.yaml`: benchmark-to-harness-policy routing manifest.

## Pair Strengths

| Benchmark | Recommended Pair | What It Is Best For |
| --- | --- | --- |
| ToolHop | `01_harness5` | Best selected 8B ToolHop pair. It is the default for long tool-use chains where the agent needs steady execution and answer commitment. |
| HotpotQA | `03_harness6` | Best selected 8B HotpotQA pair. It is preferred for multi-hop QA because it preserves evidence state and answer constraints better in the shortlist. |
| 2WikiQA | `03_harness6` | Also selected for 8B 2WikiQA, so this pair is the main 8B multi-hop QA option across both HotpotQA and 2WikiQA. |
| TMDB | `04_harness1` | Best selected 8B TMDB pair. It is strongest for API endpoint selection, schema-sensitive calls, and returning a stable final answer. |
| API-Bank | `01_harness5` | Best selected 8B API-Bank pair. It is the preferred structured tool/API workflow option for this backbone. |

## Pair Table

| Benchmark | Pair ID | Harness | Policy / Served Model |
| --- | --- | --- | --- |
| ToolHop | `01_harness5` | `rounds.round_03_01.harness_round03_01_5` | `qwen3-8B-round_03_01-harness5` |
| HotpotQA | `03_harness6` | `rounds.round_03_03.harness_round03_03_6` | `qwen3-8B-round_03_03-harness6` |
| 2WikiQA | `03_harness6` | `rounds.round_03_03.harness_round03_03_6` | `qwen3-8B-round_03_03-harness6` |
| TMDB | `04_harness1` | `rounds.round_03_04.harness_round03_04_1` | `qwen3-8B-round_03_04-harness1` |
| API-Bank | `01_harness5` | `rounds.round_03_01.harness_round03_01_5` | `qwen3-8B-round_03_01-harness5` |

Run a pair by passing `--harness_package evolved_pairs.harness_factory`, the harness module from the table, and the corresponding policy as `--model`.
