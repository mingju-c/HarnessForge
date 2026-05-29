# MATE Project Layout

This repository is organized around repeatable harness-evolution rounds. Keep
source code, datasets, model adapters, and run artifacts separated so large
experiments can be resumed and compared without guessing where files came from.

## Top-Level Roles

- `data/`: canonical local copies of benchmark and training data. Treat these
  files as read-only during experiments. The current mixed rollout data lives in
  `data/mixeddata/`. Deterministic stratified splits for one-, two-, and
  three-round evolution experiments live in `data/mixeddata/evolution_splits/`.
- `runtime/`: benchmark runtime adapters for ToolHop, API-Bank, and RestBench.
  They build task tools and compute benchmark-specific metrics.
- `mixeddata/`: mixed rollout-data adapter that dispatches to the benchmark
  runtimes above when a mixed sample needs ToolHop/SearchQA/EnvScaler tools.
- `harness_factory/`: importable harness code. Generated or hand-edited
  harness candidates should live here.
- `adapter_factory/`: LoRA/model-adapter artifacts or symlinks grouped by
  evolution round.
- `experiment_factory/`: human-readable experiment ledger: round plans,
  manifests, notes, and analysis outputs.
- `output/`: raw inference outputs, per-task JSON files, reports, and metrics.
- `storage/runs/`: per-run agent memory and auxiliary state.
- `registries/`: compact indices for harness and adapter identities.
- `tools/` and `harness_production/`: data preparation, analysis, and harness
  production utilities.

## Round Naming

Use stable round ids:

- `round_00_base`: base model plus `base_harness`; collect baseline rollouts.
- `round_01`: first evolved harness pool from the base rollouts.
- `round_02`: next harness/model iteration, if needed.

Use stable run groups under each round:

- `base_rollout`: one harness/model over a split, usually train.
- `candidate_eval`: evaluate several harness candidates.
- `trajectory_sampling`: collect high-quality trajectories for training.
- `model_eval`: evaluate harness plus trained model or adapter.

## Harness Location

Put importable candidate harnesses under:

```text
harness_factory/rounds/round_01/<harness_name>/
```

Invoke them with:

```bash
--harness_package harness_factory
--harness rounds.round_01.<harness_name>
```

Keep `harness_factory/base_harness/` as the immutable baseline. If a candidate
starts from the baseline, copy it into a new round directory and edit there.

## Adapter Location

Put or symlink model adapters under:

```text
adapter_factory/round_01/<adapter_name>/
```

Use `registries/model_adapters.yaml` to record where each adapter came from,
which trajectories trained it, and which base model it expects. Large
checkpoints can stay in an external training directory; this repository only
needs the path or symlink.

## Output Location

Use this default structure for run artifacts:

```text
output/<experiment_id>/<round_id>/<run_group>/<run_id>/
storage/runs/<experiment_id>/<round_id>/<run_group>/<run_id>/
```

For MixedData, `run_mixeddata_infer.sh` follows this structure
by default. Override `OUTPUT_ROOT`, `STORAGE_ROOT`, or `RUN_ID` when resuming or
when an older layout is needed.

## Recommended One-Round Workflow

1. Run `round_00_base/base_rollout` on `mixeddata` train.
2. Summarize metrics by benchmark, not only by overall score.
3. Generate or hand-edit harness candidates under `harness_factory/rounds/round_01/`.
4. Evaluate candidates on `mixeddata` val and small external benchmark
   slices.
5. Use the best harness candidates for trajectory sampling.
6. Train model adapters and register them under `adapter_factory/round_01/`.
7. Evaluate the best harness-plus-model combinations on the final benchmark
   suite.
