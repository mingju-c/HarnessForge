# Shared mixed-task SFT recipe

This shared reference implementation applies the **final filtering rules
specified by the maintainers** to both the 4B and 8B workspaces. QA trajectories
require `score == 1` and `answer_correct == 1`. EnvScaler trajectories require
`envscaler_score >= 0.9` and `envscaler_done == 1`. The recipe version is
`mixed_sft_v2`; evaluation scores continue to use `paper_c1_v1`.

The implementation is [`tools/prepare_mixed_sft.py`](../tools/prepare_mixed_sft.py)
at the repository root; each workspace has a small wrapper with the same name.
The cleaner needs only Python's standard library. Training needs a separate
training environment and model checkpoint.

## 1. Collect trajectories with explicit source declarations

Run from either workspace. Adjust the harness, checkpoint alias, round, and
dataset identifiers together. The file below must be an actual evolution/train
split; the flag records a declaration and does not independently certify the
split. Keep held-out benchmark test examples out of this workflow.

```bash
python run_infer.py \
  --benchmark mixeddata \
  --infile /absolute/path/to/evolution_round01.jsonl \
  --harness_package harness_factory \
  --harness rounds.round_01.harness_round01_2 \
  --model YOUR_SERVED_PARENT_POLICY \
  --model-alias policy_round00 \
  --model-backend local \
  --api-base "$OPENAI_BASE_URL" \
  --api-key "$OPENAI_API_KEY" \
  --registry-round round01 \
  --registry-dataset mixed_evolution_round01 \
  --data-split evolution \
  --concurrency 1 \
  --max_steps 50 \
  --outfile output/policy_alignment/round01_harness2/results.jsonl \
  --direct_output_dir output/policy_alignment/round01_harness2 \
  --memory_storage_dir storage/policy_alignment/round01_harness2
```

The mixed-data runner records `round_id`, `harness`, `policy_id`, `dataset_id`,
`data_split`, the model/adapter identifier, and input path/SHA-256 with each
result, including failed executions. The registry flags also supply these
declarations when registry recording is disabled. Resume rejects conflicts
with recorded provenance. For an explicitly declared split, it also rejects
old rows without provenance. Use unique policy aliases for distinct checkpoints.

ToolHop items must carry their original `sub_task` scoring labels. Old
EM/subEM results cannot simply be relabelled `paper_c1_v1`; re-score saved
trajectories with the required evidence or collect new trajectories first.

## 2. Declare one round and harness-policy pair per build

Copy [`sources.example.json`](../examples/mixed_sft/sources.example.json) into
your run directory and adjust it. Paths in `sources` are relative to the
manifest's directory, not the current shell directory. Each source may be a
results JSONL file, one task JSON file, or a directory of numeric task JSON
files. Do not list both representations unless you intend them to be deduplicated.

```json
{
  "round_id": "round01",
  "harness": "rounds.round_01.harness_round01_2",
  "policy_id": "policy_round00",
  "dataset_id": "mixed_evolution_round01",
  "data_split": "evolution",
  "sources": ["results.jsonl"]
}
```

Build each child-policy dataset from the corresponding candidate's accepted
rollouts in the current round. The source check rejects conflicting round or
harness metadata, including records from earlier rounds or sibling candidates.
Parent-policy initialization is separate from the new supervision dataset.

Every row must match those five declarations. Missing metadata aborts by
default; conflicting metadata always aborts. For independently checked older
data, `--allow-declared-provenance` permits missing fields and explicitly marks
the weaker check as `manifest_declared`. It does not permit a scoring-version
override, a conflicting round/pair, or declared validation/test data.

Metadata and hashes make source handling auditable. They do not prove that
dataset labels are truthful or that historical selection was test-independent.

## 3. Apply a named, explicit configuration

From either workspace, using the manifest saved beside `results.jsonl`:

```bash
python tools/prepare_mixed_sft.py \
  --manifest output/policy_alignment/round01_harness2/sources.json \
  --config ../examples/mixed_sft/final_full.json \
  --dataset-name round01_harness2 \
  --output-dir data/sft/round01_harness2_v2
```

| Configuration | Acceptance and representation |
| --- | --- |
| `final_full.json` (default recipe) | QA: score 1 and correct answer; EnvScaler: reward at least 0.9 and done; one full dialogue per task |
| `final_prefix.json` | Identical acceptance rules; one prefix per assistant turn |

Both examples use the same final acceptance policy. There is no automatic
threshold relaxation, round-based tightening, balancing, terminal downsampling,
or minimum-sample quota. Reuse the same configuration across compared branches.
An explicit change to the EnvScaler threshold is recorded in the output config
and hash; the supplied final configurations both use 0.9. QA score thresholds
must stay at 1, and both QA families also require `answer_correct == 1`.

All modes require `status=success` and `scoring_version=paper_c1_v1` and check
that the task score agrees with its components:

- ToolHop: `score = 0.5 * answer_correct + 0.5 * path_score`; SFT requires
  `score == 1` and `answer_correct == 1`.
- SearchQA: evaluation uses `score = answer_f1`; SFT additionally requires
  `score == 1` and `answer_correct == 1`. A token F1 of 1 alone is insufficient
  when the normalized final answer is not an exact match.
- EnvScaler: `score` must agree with `envscaler_score`; SFT applies the 0.9
  threshold directly to `envscaler_score` and requires `envscaler_done == 1`.

These acceptance thresholds govern SFT data selection, not the mixed evaluator
or Pareto objectives. Partial-credit rollouts still contribute their actual
scores to evaluation, regardless of whether SFT accepts them.

## 4. Dialogue handling and deduplication

The cleaner consumes the runner's `agent_messages` text blocks and
`Calling tools:` payloads (JSON or Python literals), as well as native
assistant `tool_calls`. It preserves plans, summaries, valid actions, and the
terminal action. Existing system messages are retained; a missing system
prompt is not invented. Adjacent same-role messages are merged.

Tool observations become user-side context, prefixed with `[Tool observation]`;
they are never assistant targets. Configure the trainer with
`train_on_prompt: false`. The cleaner rejects a whole trajectory when it
contains an execution error or a configured failed/guarded observation marker.
It does not remove a state-changing action and keep the dependent continuation.
Repeated nonterminal calls are retained because repeating a call can be valid
in a stateful environment. Marker matching is a conservative text filter,
not a semantic execution verifier; inspect rejection counts for false positives.

QA uses `final_answer`/`submit_answer`; EnvScaler uses
`complete_task`/`task_completed` or `chat_with_user(content="Task Completed")`.
A terminal call must be alone in its batch. Terminal observations and plain
text echoes/tails are removed, but a later tool call causes rejection.
Malformed calls, missing observations, unsupported content, orphan tool
responses, and invalid dialogue alternation are rejected.

One trajectory is retained per dataset/task-family/task-ID (falling back to
normalized question text when an ID is absent). Selection prefers higher score,
then shorter serialized dialogue, then content hash. The audit records every
discarded duplicate. Source dataset IDs and task IDs must be stable and unique.

Task groups are assigned to train/eval with a deterministic hash of seed,
task family, and normalized question. This keeps identical questions together
even across differing branch acceptance sets, provided the seed and eval ratio
are unchanged. Prefix expansion happens **after** this split. The eval ratio
is approximate; small datasets can have an empty partition. The generated
eval set is an internal SFT holdout, not an independent benchmark validation set.
Paraphrased duplicates are not detected.

## 5. Outputs and training

The output directory must be new or empty. It contains:

- `train.jsonl`, `eval.jsonl`: ShareGPT-style data with per-sample provenance.
- `dataset_info.json`: LLaMA-Factory dataset registration.
- `manifest.json`: resolved recipe, source-file hashes, script/config hashes,
  source declarations, and provenance override status.
- `stats.json`, `audit.jsonl`: accepted/rejected counts, reasons and source rows.
- `training_options.json`: required loss-mask settings for the chosen mode.

The command exits unsuccessfully if no training samples survive; the audit is
still written. Correct the source/configuration deliberately rather than
silently relaxing thresholds.

Use the bundled LLaMA-Factory's `mask_history` parameter:

| Mode | `train_on_prompt` | `mask_history` |
| --- | --- | --- |
| Full | `false` | `false` — supervise all assistant turns |
| Prefix | `false` | `true` — supervise only the final assistant turn per prefix |

The [training YAML template](../examples/mixed_sft/llamafactory.example.yaml)
is a starting point for the full mode. Set its model, dataset/output paths,
model-compatible chat template, and hardware settings before launching it.
For prefix mode, set `mask_history: true`. Point the trainer directly at the
cleaned directory; do not rebuild trainer data from the original raw rollouts.
If `eval.jsonl` is empty, omit `eval_dataset` and disable evaluation. Do not
enable a second random `val_size` split.

The cleaner does not tokenize or check the model's context limit. Before a real
training run, inspect tokenized lengths and truncation with the selected
tokenizer and `cutoff_len`; truncation can remove supervision, including terminal
actions. Model/hardware-dependent hyperparameters in the example are not a
reproduction claim. No model training is performed by the cleaner.

## Tool cleanup and checks

Seven round-specific development/test cleaners and their temporary archive
directories have been removed. Their source remains in Git history. See the
[tool directory index](tools_index.md) for the complete cleanup scope and retained
utilities. Other standalone ToolHop/trainer utilities remain available, but
they are not steps in this shared mixed-task recipe.

```bash
# Run from repository root; no model calls or training dependencies needed.
python -B -m unittest discover -s tests -p test_mixed_sft.py -v
```
