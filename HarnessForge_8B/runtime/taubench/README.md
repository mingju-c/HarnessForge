# tau-bench adapter for MATE

This adapter runs tau-bench tasks through the existing MATE agent loop.

## Environment

Create one virtual environment for MATE plus tau-bench:

```bash
cd .
python3 -m venv .venv-taubench
source .venv-taubench/bin/activate
python3 -m pip install -U pip
python3 -m pip install -r requirements.txt
python3 -m pip install -e <TAU_BENCH_ROOT>
```

Set model credentials:

```bash
export OPENAI_API_KEY="..."
export OPENAI_BASE_URL="..."  # optional for OpenAI-compatible task model
```

The MATE task model and the tau-bench user simulator can use different models.

## Smoke Test

Start with retail dev and one or two tasks:

```bash
cd .
source .venv-taubench/bin/activate

python3 run_infer.py \
  --benchmark taubench \
  --taubench-env retail \
  --taubench-split dev \
  --sample_num 2 \
  --concurrency 1 \
  --max_steps 40 \
  --harness_package harness_factory \
  --harness base_harness \
  --model gpt-4o \
  --model-backend api \
  --taubench-user-model gpt-4o \
  --taubench-user-model-provider openai
```

Run a specific task by 1-based index:

```bash
python3 run_infer.py \
  --benchmark taubench_retail_dev \
  --task_indices 1 \
  --concurrency 1 \
  --max_steps 40 \
  --harness_package harness_factory \
  --harness base_harness \
  --model gpt-4o \
  --model-backend api
```

## Available Selectors

- `--benchmark taubench --taubench-env retail --taubench-split dev`
- `--benchmark taubench_retail_dev`
- `--benchmark taubench_retail_test`
- `--benchmark taubench_retail_train`
- `--benchmark taubench_airline_test`

Task counts in this checkout:

- retail train: 500
- retail dev: 20
- retail test: 115
- airline test: 50

## Adapter Behavior

- Each MATE sample creates one tau-bench environment.
- The task prompt contains the domain policy and the initial simulated user message.
- The available tools are the tau-bench domain tools plus `respond`.
- `respond(content)` sends one message to the tau-bench user simulator.
- MATE is configured with `max_tool_calls_per_step=1` for tau-bench, matching the original tau-bench agent behavior of using the first tool call per step.
- Reward is taken directly from tau-bench, not from an LLM judge.

Outputs include `taubench_reward`, `taubench_done`, `taubench_info`, and `taubench_events`.
