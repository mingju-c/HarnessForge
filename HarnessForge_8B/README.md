# HarnessForge 8B Workspace

This folder is the 8B backbone workspace for **HarnessForge: Joint Harness and Policy Evolution for Adaptive Agent Systems**. It contains the generated harnesses, curated evolved pairs, benchmark wrappers, harness-production prompts, and policy-alignment utilities for the 8B track.

## Structure

```text
HarnessForge_8B/
|-- README.md
|-- run_infer.py                    # unified benchmark runner
|-- run_tooluse_suite.sh            # ToolHop/TMDB/API-Bank suite wrapper
|-- evolved_pairs/                  # curated round-3 harness-policy pairs
|   |-- README.md
|   |-- pairs.yaml
|   |-- harness_factory/            # selected harness bundles
|   `-- policy_factory/             # policy manifests; no checkpoints
|-- harness_factory/                # full generated harness pool
|   |-- base_harness/
|   `-- rounds/
|-- harness_production/             # API-driven tailoring pipeline
|   |-- 01_module_localization.yaml
|   |-- 02_improvement_directions.yaml
|   |-- 03_harness_generation.yaml
|   `-- run_harness_production.py
|-- runtime/                        # runtime adapters and metrics
|-- tools/                          # data cleaning and SFT utilities
|-- registries/                     # harness/model metadata
|-- data/                           # optional local data/manifests
`-- storage/, output/               # local-only generated artifacts
```

## Quick Start

```bash
cd /path/to/HarnessForge/HarnessForge_8B

conda create -n harnessforge python=3.10 -y
conda activate harnessforge
python -m pip install -U pip setuptools wheel
python -m pip install -r requirements.txt
cp .env.example .env
```

Minimal model endpoint variables:

```bash
OPENAI_BASE_URL=<OPENAI_COMPATIBLE_BASE_URL>
OPENAI_API_KEY=EMPTY
PLANNING_MODEL=<served-model-name>
EXECUTE_MODEL=<served-model-name>
JUDGE_MODEL=<optional-judge-model-name>
```

Benchmark keys are minimal: ToolHop and API-Bank use the shared `../eval_bench/` assets and are local/offline; TMDB needs `TMDB_ACCESS_TOKEN` or `TMDB_API_KEY` only for live endpoint execution.

## Reproduce An Evolved Pair

Recommended benchmark-specific pairs are listed in `evolved_pairs/README.md` and `evolved_pairs/pairs.yaml`. Large policy checkpoints are not stored here; serve the policy name through your OpenAI-compatible endpoint.

```bash
export OPENAI_BASE_URL=<OPENAI_COMPATIBLE_BASE_URL>
export OPENAI_API_KEY=${OPENAI_API_KEY:-EMPTY}

python ./run_infer.py \
  --benchmark toolhop \
  --infile test \
  --harness_package evolved_pairs.harness_factory \
  --harness rounds.round_03_01.harness_round03_01_5 \
  --model qwen3-8B-round_03_01-harness5 \
  --model-backend local \
  --api-base "$OPENAI_BASE_URL" \
  --api-key "$OPENAI_API_KEY" \
  --concurrency 1 \
  --max_steps 50 \
  --direct_output_dir output/reproduce/8b_evolved_pair_toolhop \
  --memory_storage_dir storage/reproduce/8b_evolved_pair_toolhop
```

To run the three-benchmark suite with one harness/model pair:

```bash
bash ./run_tooluse_suite.sh \
  --harness rounds.round_03_01.harness_round03_01_5 \
  --model qwen3-8B-round_03_01-harness5 \
  --api-base "$OPENAI_BASE_URL" \
  --api-key "$OPENAI_API_KEY" \
  --benches toolhop,tmdb,api_bank \
  --toolhop-infile test \
  --concurrency 1 \
  --max-steps 50 \
  --run-id reproduce_8b_evolved_pair
```

## Tailor A New Harness

Harness tailoring has four stages: location, improvement, generation, and test.

```bash
python harness_production/run_harness_production.py --help
python harness_production/04_validation_retry.py --help
```

Production artifacts are written under `harness_production/<round_id>/`. Generated candidates are written under `harness_factory/rounds/<target_round>/<candidate_name>/` when `--write-candidate` is used.

## Policy Alignment

Trajectory cleaning and SFT-data construction scripts live in `tools/`. Use the shared `../LlamaFactory/` directory for SFT launch/configuration; model weights, checkpoints, and generated training data stay outside this workspace:

```text
tools/prepare_toolhop_rollout_sft.py
tools/prepare_trainer_harness_data.py
tools/create_mixeddata_evolution_splits.py
tools/split_trainer_dataset_bundle.py
```

The repo prepares trainer-ready data. Model training itself is expected to run in your SFT stack, for example LLaMA-Factory or an internal trainer.

## Data And Git Hygiene

Keep `.env`, `output/`, `storage/`, raw rollouts, cleaned SFT data, and checkpoints local. `data/mixeddata` is optional and can be omitted from a lightweight GitHub release; the full local copy is large because it contains raw data plus repeated split products.
