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
