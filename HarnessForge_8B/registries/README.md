# Harness Pool Registry

`harness_pool.yaml` is the lightweight source of truth for harness identities
and run summaries. It does not store raw trajectories; it points to result files
and keeps compact metrics such as accuracy, valid-answer rate, path/process
score, average steps, latency, and token cost.

`model_adapters.yaml` is the matching lightweight index for LoRA/model adapters.
It should record the base model, adapter path, training data, and intended
evaluation pairings. Large checkpoint files should stay under `adapter_factory/`
or an external checkpoint directory.

Typical manual workflow:

```bash
python tools/harness_pool_registry.py discover \
  --registry-file registries/harness_pool.yaml \
  --package harness_factory

python tools/harness_pool_registry.py record-run \
  --registry-file registries/harness_pool.yaml \
  --harness base_harness \
  --round round_0 \
  --dataset toolhop_round_1 \
  --model qwen3-aevolve \
  --model-backend local \
  --results output/toolhop/base/results.jsonl \
  --run-dir output/toolhop/base

python tools/harness_pool_registry.py topk \
  --registry-file registries/harness_pool.yaml \
  --round round_0 \
  --dataset toolhop_round_1 \
  --k 5 \
  --output experiment_factory/toolhop/round_0/analysis/topk_harnesses.json
```

`run_infer.py` can also update this registry directly when called with
`--record-harness-registry`.

## Mixed evolution performance

For `paper_c1_v1` mixed-data runs, `primary_score` is the micro-average
`avg_score`, including EnvScaler completion rewards. QA-only fields remain
unchanged. Accuracy, valid-answer rate, path score, and tool-call counts do not
add bonuses or penalties to this mixed performance value.

The default `tools/half_select_harnesses.py` retains six independent objectives:
maximize `primary_score`, `accuracy`, `valid_answer_rate`; minimize `avg_tokens`,
`avg_elapsed_time`, `avg_tool_calls`. These extra objectives are not weighted
components of `Perf` and are not equivalent to the paper's three-objective
vector. To select with three objectives, explicitly pass:

```text
--quality-metric primary_score --cost-metric avg_tokens --cost-metric avg_elapsed_time
```

Run records and their `latest` views retain `scoring_version`,
`score_aggregation`, and `avg_score`. Selection outputs record the actual
objectives. Historical unversioned scores must be re-evaluated before selection
with the corrected scoring version. Do not relabel old scores or overwrite the
published archives to imply they used the corrected evaluator. See
[the task scorer](../mixeddata/mixed_reward.py) for required ToolHop labels and
[the mixed-data evaluator](../mixeddata/evaluation.py) for aggregation details.
