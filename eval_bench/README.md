# MATE Eval Bench Bundle

Bench assets have been collected here so evaluation can be launched from the `MATE_3rounds` root.

- `qa/`: AgentGym SearchQA-style offline search eval data, builder, and retriever env wrapper.
- `tau-bench/`: tau-bench source package, runtime adapter, and env file.
- `toolhop/`: ToolHop data/splits and runtime wrapper.
- `api-bank/`: API-Bank APIs, databases, samples, and runtime wrapper.
- `tmdb/`: RestBench TMDB dataset/spec/runtime and env file.

Use the per-bench `scripts/run_*_eval.sh` wrappers, or call `run_infer.py` directly; benchmark defaults now prefer these local paths.
