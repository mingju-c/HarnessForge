# ToolHop Eval Bench

This bench keeps the compact final blind test file used for reproducible evaluation.

- `data/toolhop_final_blind_test.json`: ToolHop final blind test records.

Run from this workspace:

```bash
bash eval_bench/toolhop/scripts/run_toolhop_eval.sh --model qwen3-4b-base --model-backend local --api-base <OPENAI_COMPATIBLE_BASE_URL> --api-key EMPTY --harness_package harness_factory --harness base_harness
```
