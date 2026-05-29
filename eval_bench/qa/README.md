# QA Offline Search Eval Bench

This bench contains the compact SearchQA-style evaluation files used by `run_infer.py`.

- `data/hotpotqa.jsonl`: 150 HotpotQA evaluation records.
- `data/2wikimultihopqa.jsonl`: 150 2WikiMultiHopQA evaluation records.
- `data/all.jsonl`: HotpotQA + 2WikiMultiHopQA, 300 records total.
- `retrieve_data`: external/local AgentGym SearchQA E5/FAISS assets are expected outside the repo because the payload is large.

The original builder source splits are intentionally not committed. To rebuild the compact eval files, provide local source data explicitly:

```bash
python eval_bench/qa/scripts/build_searchqa_eval.py   --source-data-dir /path/to/source_data   --sources hotpotqa,2wikimultihopqa   --count 150   --seed 42
```

Run from this workspace:

```bash
DATASET=hotpotqa bash eval_bench/qa/scripts/run_searchqa_eval.sh --model qwen3-4b-base --model-backend local --api-base <OPENAI_COMPATIBLE_BASE_URL> --api-key EMPTY --harness_package harness_factory --harness base_harness
DATASET=2wikimultihopqa bash eval_bench/qa/scripts/run_searchqa_eval.sh --model qwen3-4b-base --model-backend local --api-base <OPENAI_COMPATIBLE_BASE_URL> --api-key EMPTY --harness_package harness_factory --harness base_harness
```
