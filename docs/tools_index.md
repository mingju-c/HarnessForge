# Tool directory index

The workspace `tools/` directories contain runtime dependencies and standalone
command-line utilities. They cannot be removed as a whole: `run_infer.py`
imports the registry and rollout provenance modules. The canonical mixed-task
SFT recipe is shared at the repository root.

## Scoring, selection, and SFT entry points

| Purpose | 4B | 8B |
| --- | --- | --- |
| Task-aware scoring | [mixed_reward.py](../HarnessForge_4B/mixeddata/mixed_reward.py) | [mixed_reward.py](../HarnessForge_8B/mixeddata/mixed_reward.py) |
| Mixed micro-average | [evaluation.py](../HarnessForge_4B/mixeddata/evaluation.py) | [evaluation.py](../HarnessForge_8B/mixeddata/evaluation.py) |
| Registry and performance score | [harness_pool_registry.py](../HarnessForge_4B/tools/harness_pool_registry.py) | [harness_pool_registry.py](../HarnessForge_8B/tools/harness_pool_registry.py) |
| Pareto selection (six defaults; explicit three-objective mode) | [half_select_harnesses.py](../HarnessForge_4B/tools/half_select_harnesses.py) | [half_select_harnesses.py](../HarnessForge_8B/tools/half_select_harnesses.py) |
| Rollout source metadata and resume checks | [rollout_provenance.py](../HarnessForge_4B/tools/rollout_provenance.py) | [rollout_provenance.py](../HarnessForge_8B/tools/rollout_provenance.py) |
| SFT command wrapper | [prepare_mixed_sft.py](../HarnessForge_4B/tools/prepare_mixed_sft.py) | [prepare_mixed_sft.py](../HarnessForge_8B/tools/prepare_mixed_sft.py) |

Both SFT wrappers execute the same [shared implementation](../tools/prepare_mixed_sft.py).
See the [SFT workflow](mixed_sft.md), [configuration examples](../examples/mixed_sft/),
and [regression tests](../tests/).

## Other retained utilities

These are standalone commands, so the absence of imports elsewhere does not
make them unused code. They serve data preparation, benchmark evaluation, or
alternative trainer formats; they are not additional steps in the shared SFT recipe.

| Script | Purpose and scope | Workspaces |
| --- | --- | --- |
| `create_mixeddata_evolution_splits.py` | Deterministic stratified partitions of an input evolution pool into one, two, or three rounds; does not orchestrate candidate selection. | [4B](../HarnessForge_4B/tools/create_mixeddata_evolution_splits.py), [8B](../HarnessForge_8B/tools/create_mixeddata_evolution_splits.py) |
| `prepare_mixeddata_for_mate.py` | Convert the existing parquet/raw data format to runner input; requires pandas and a parquet engine. The filename retains the earlier MATE naming. | [4B](../HarnessForge_4B/tools/prepare_mixeddata_for_mate.py), [8B](../HarnessForge_8B/tools/prepare_mixeddata_for_mate.py) |
| `split_toolhop_online_rounds.py` | Split raw ToolHop tasks into development rounds and a held-out test set before running experiments. | [4B](../HarnessForge_4B/tools/split_toolhop_online_rounds.py), [8B](../HarnessForge_8B/tools/split_toolhop_online_rounds.py) |
| `run_tooluse_baseline.py` | Parameterized launcher for standalone ToolHop, RestBench, and API-Bank evaluation; supports `--dry-run`. | [4B](../HarnessForge_4B/tools/run_tooluse_baseline.py), [8B](../HarnessForge_8B/tools/run_tooluse_baseline.py) |
| `prepare_toolhop_rollout_sft.py` | Older standalone ToolHop turn-level SFT export. Its acceptance tiers differ from the shared mixed-task recipe. | [4B](../HarnessForge_4B/tools/prepare_toolhop_rollout_sft.py), [8B](../HarnessForge_8B/tools/prepare_toolhop_rollout_sft.py) |
| `prepare_trainer_harness_data.py` | Older actor/candidate export to SFT/DPO bundles. Does not provide the shared recipe's source and scoring-version checks. | [4B](../HarnessForge_4B/tools/prepare_trainer_harness_data.py), [8B](../HarnessForge_8B/tools/prepare_trainer_harness_data.py) |
| `split_trainer_dataset_bundle.py` | Split those older trainer bundles by instance ID. The shared cleaner already performs its own task-group split. | [4B](../HarnessForge_4B/tools/split_trainer_dataset_bundle.py), [8B](../HarnessForge_8B/tools/split_trainer_dataset_bundle.py) |
| `summarize_sft_lengths.py` | Inspect message lengths; optional token estimates use a fixed Qwen-style serialization, not the trainer's actual preprocessing. Supply `--data-file` and `--output-dir` to override old defaults. | [4B](../HarnessForge_4B/tools/summarize_sft_lengths.py) |
| `update_harness_archive_from_design.py` | Generate archive entries from harness design files; supports prompt inspection and calls a configured model when generating entries. | [4B](../HarnessForge_4B/tools/update_harness_archive_from_design.py) |

Use each command's `--help` for arguments. `rollout_provenance.py` is an imported
module, not a command-line program. The two workspaces intentionally retain
only the utilities they contain; a missing counterpart is not an implied feature.

## Removed utilities

Seven round-specific SFT development/test scripts were removed from the
working tree, along with their temporary `legacy_sft/` directories. Their
source remains available in Git history. New mixed-task SFT work uses
`prepare_mixed_sft.py` and explicit configuration files.

The cleanup also removed these unreferenced utilities:

| Script | Reason | Copies removed |
| --- | --- | --- |
| `archive_round00_seed_profile.py` | Fixed round00 paths, hard-coded candidate assessments, and a legacy scoring proxy. | 4B and 8B |
| `generate_toolhop_harness_analysis.py` | Fixed round1 run layout and harness1–7 loop. | 4B and 8B |
| `generate_toolhop_harness_reports.py` | Old round1/test report layout and evolution-prompt generation, separate from the current runner reports. | 4B and 8B |
| `prepare_toolhop_cross_harness_dpo.py` | Fixed round1 harness2/4/6 input files rather than configurable candidate sources. | 4B and 8B |
| `create_stratified_sft_split.py` | Row-level splitting can separate prefixes of the same task; the shared cleaner splits task groups before prefix expansion. | 4B |

Deleting these files does not determine which scripts generated historical
experimental results. Original run records remain necessary for that question.
