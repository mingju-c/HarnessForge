# Harness Production Prompts

Canonical flow is three prompts plus one executable validator:

1. `01_module_localization.yaml`
   - Input: winner/base harness code, metrics, failed trajectories, successful trajectories.
   - Output: module-localized diagnosis.
   - Key question: each failure is mainly Planning, Action, Memory, Builder, or Interface?

2. `02_improvement_directions.yaml`
   - Input: Stage 1 localization report plus related harness pool/archive examples.
   - Output: improvement direction brief.
   - Key question: what should the next harness preserve, borrow, avoid, and change by module?

3. `03_harness_generation.yaml`
   - Input: Stage 1 report, Stage 2 brief, selected examples, winner harness template.
   - Output: one complete harness candidate.
   - Key question: how should the meta agent implement the next harness?

4. `04_validation_retry.py`
   - Input: generated harness files plus validation logs.
   - Output: validation report and, when needed, bounded small repair edits.
   - Key question: does the generated harness import, instantiate, and survive a minimal smoke check? If not, can it be fixed without redesign?
   - Note: missing project dependencies are reported as `failed_environment` and are not sent to auto-fix.
   - Closed loop: validator runs first; if the verdict is `failed_static`, `failed_import`, or `failed_build`, a repair agent patches the harness and validation retries. If retries are exhausted, the report returns `needs_regeneration` for a new Stage 3 generation.

The `参考/` directory keeps the original memory-system analysis/generation prompts
used as style references. Other scripts and older prompt catalogs are legacy helpers;
the main harness-production design is the four files above.

## API Pipeline Script

`run_harness_production.py` runs the three YAML prompts through an OpenAI-compatible API and saves reproducible phase artifacts in this production directory. It loads `.env` from the outer HarnessForge root and this 4B project root, then uses:

- `HARNESS_ANALYSIS_MODEL` or `ANALYSIS_MODEL` for Stage 1.
- `HARNESS_DIRECTION_MODEL` or `GENERATION_MODEL` for Stage 2.
- `HARNESS_GENERATION_MODEL` or `GENERATION_MODEL` for Stage 3.
- `HARNESS_PRODUCTION_MODEL` / `DEFAULT_MODEL` / `OPENAI_MODEL` as fallback.

Example:

```bash
cd /path/to/HarnessForge/HarnessForge_4B
python harness_production/run_harness_production.py \
  --stage all \
  --round-id round3_4 \
  --winner-harness-name harness_round03_04_1 \
  --winner-harness-path harness_factory/rounds/round_03_04/harness_round03_04_1 \
  --metrics-summary-file path/to/metrics_summary.md \
  --failure-summary-file path/to/failure_summary.md \
  --trajectory-overview-file path/to/trajectory_overview.md \
  --failure-trajectory-samples-file path/to/failed_samples.md \
  --success-trajectory-samples-file path/to/success_samples.md \
  --harness-pool-overview-file registries/harness_archive.yaml \
  --target-round round_03_05 \
  --candidate-name harness_round03_05_1 \
  --write-candidate
```

With `--round-id round3_4`, outputs are written directly to `harness_production/round3_4/`: `module_localization_report.md`, `improvement_direction_brief.md`, `harness_generation.raw.md`, rendered prompts, and `state.json`. Use `--dry-run` to render prompts without calling the API. Use `04_validation_retry.py` after Stage 3 writes a candidate.

Example validation command:

```bash
python3 harness_production/04_validation_retry.py \
  --candidate-path harness_factory/rounds/round_01/<candidate_name> \
  --fix-model "${HARNESS_VALIDATION_FIX_MODEL:-gpt-4.1-mini}" \
  --max-fix-attempts 3
```

Repair backends:

- `--repair-agent json_model` is the default lightweight repair agent. It asks the fixed model for complete revised file contents.
- `--repair-agent mini_swe` uses mini-swe-agent, if available locally, to edit files in the project workspace and rerun validation.

Verdict semantics:

- `passed` / `fixed_after_retry`: accept the harness for benchmark evaluation.
- `failed_environment`: fix the Python environment, then rerun validation.
- `needs_regeneration`: feed `validation_retry_report.json` back into Stage 3 and generate a fresh harness candidate.
