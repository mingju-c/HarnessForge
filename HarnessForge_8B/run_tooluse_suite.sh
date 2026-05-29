#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

HARNESS_PACKAGE_DEFAULT="harness_factory"
HARNESS=""
MODEL=""
MODEL_BACKEND="local"
API_BASE="${OPENAI_BASE_URL:-${OPENAI_API_URL:-}}"
API_KEY="EMPTY"
RUN_ID=""
OUTPUT_ROOT="$PROJECT_ROOT/output"
STORAGE_ROOT="$PROJECT_ROOT/storage"
CONCURRENCY=1
MAX_STEPS=50
TOOLHOP_INFILE="test"
BENCHES="toolhop,tmdb,api_bank"
HARNESS_PACKAGE="$HARNESS_PACKAGE_DEFAULT"
MEMORY_PROVIDER=""
MEMORY_WRITE_ONLY="true"
STREAM_LOGS="true"

usage() {
  cat <<'USAGE'
Usage:
  bash ./run_tooluse_suite.sh --harness <name> --model <model-id> [options]

Required:
  --harness NAME             Harness bundle name, e.g. base_harness
  --model MODEL_ID            Served model name, e.g. Qwen3-8B

Common options:
  --api-base URL              OpenAI-compatible endpoint base. Defaults to OPENAI_BASE_URL or OPENAI_API_URL.
  --api-key KEY               API key for endpoint. Default: EMPTY
  --model-backend NAME        local or api. Default: local
  --harness-package NAME     Harness package. Default: harness_factory
  --run-id ID                 Output run id. Default: tooluse_<harness>_<model>_<timestamp>
  --output-root DIR           Root for outputs. Default: ./output
  --storage-root DIR          Root for memory storage. Default: ./storage
  --concurrency N             Evaluation concurrency. Default: 1
  --max-steps N               Max harness action steps per task. Default: 50
  --benches LIST              Comma list: toolhop,tmdb,api_bank. Default: all three
  --toolhop-infile VALUE      ToolHop input selector/path. Default: test (195 blind-test set)
  --memory-provider NAME      Optional memory provider override
  --memory-write-only BOOL    Store memory but do not retrieve old memory. Default: true
  --stream-logs BOOL          Also print each bench log to terminal. Default: true

Examples:
  bash ./run_tooluse_suite.sh \
    --harness base_harness \
    --model Qwen3-8B \
    --api-base <OPENAI_COMPATIBLE_BASE_URL>

  bash ./run_tooluse_suite.sh \
    --harness evolved_harness_001 \
    --model grpo-step50 \
    --api-base <OPENAI_COMPATIBLE_BASE_URL> \
    --benches toolhop,tmdb
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --harness) HARNESS="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --api-base) API_BASE="$2"; shift 2 ;;
    --api-key) API_KEY="$2"; shift 2 ;;
    --model-backend) MODEL_BACKEND="$2"; shift 2 ;;
    --harness-package) HARNESS_PACKAGE="$2"; shift 2 ;;
    --run-id) RUN_ID="$2"; shift 2 ;;
    --output-root) OUTPUT_ROOT="$2"; shift 2 ;;
    --storage-root) STORAGE_ROOT="$2"; shift 2 ;;
    --concurrency) CONCURRENCY="$2"; shift 2 ;;
    --max-steps) MAX_STEPS="$2"; shift 2 ;;
    --benches) BENCHES="$2"; shift 2 ;;
    --toolhop-infile) TOOLHOP_INFILE="$2"; shift 2 ;;
    --memory-provider) MEMORY_PROVIDER="$2"; shift 2 ;;
    --memory-write-only) MEMORY_WRITE_ONLY="$2"; shift 2 ;;
    --stream-logs) STREAM_LOGS="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$HARNESS" || -z "$MODEL" ]]; then
  usage
  exit 2
fi
if [[ -z "$API_BASE" ]]; then
  echo "Error: pass --api-base or set OPENAI_BASE_URL/OPENAI_API_URL." >&2
  exit 2
fi

sanitize() {
  printf '%s' "$1" | sed -E 's/[^A-Za-z0-9._-]+/_/g; s/^_+//; s/_+$//'
}

is_truthy() {
  case "$1" in
    1|true|True|TRUE|yes|Yes|YES|y|Y|on|On|ON) return 0 ;;
    *) return 1 ;;
  esac
}

MODEL_SAFE="$(sanitize "$MODEL")"
HARNESS_SAFE="$(sanitize "$HARNESS")"
if [[ -z "$RUN_ID" ]]; then
  RUN_ID="tooluse_${HARNESS_SAFE}_${MODEL_SAFE}_$(date +%Y%m%d_%H%M%S)"
fi

RUN_ROOT="$OUTPUT_ROOT/$RUN_ID"
RUN_STORAGE_ROOT="$STORAGE_ROOT/$RUN_ID"

mkdir -p "$RUN_ROOT/logs" "$RUN_STORAGE_ROOT"

COMMON_ARGS=(
  --harness_package "$HARNESS_PACKAGE"
  --harness "$HARNESS"
  --model "$MODEL"
  --model-backend "$MODEL_BACKEND"
  --api-base "$API_BASE"
  --api-key "$API_KEY"
  --concurrency "$CONCURRENCY"
  --max_steps "$MAX_STEPS"
  --memory-write-only "$MEMORY_WRITE_ONLY"
)

if [[ -n "$MEMORY_PROVIDER" ]]; then
  COMMON_ARGS+=(--memory_provider "$MEMORY_PROVIDER")
fi

run_bench() {
  local bench="$1"
  local benchmark="$2"
  local run_name="$3"
  shift 3

  local direct_output_dir="$RUN_ROOT/$HARNESS_SAFE/$MODEL_SAFE/$run_name"
  local memory_storage_dir="$RUN_STORAGE_ROOT/$HARNESS_SAFE/$MODEL_SAFE/$run_name"
  local outfile="$direct_output_dir/results.jsonl"
  local logfile="$RUN_ROOT/logs/${run_name}.log"
  local cmd

  mkdir -p "$direct_output_dir" "$memory_storage_dir"

  echo "[$(date)] running ${bench}: harness=${HARNESS}, model=${MODEL}, output=${direct_output_dir}"
  cmd=(
    "$PYTHON_BIN" "$PROJECT_ROOT/run_infer.py" \
    --benchmark "$benchmark" \
    "${COMMON_ARGS[@]}" \
    "$@" \
    --outfile "$outfile" \
    --direct_output_dir "$direct_output_dir" \
    --memory_storage_dir "$memory_storage_dir"
  )
  if is_truthy "$STREAM_LOGS"; then
    "${cmd[@]}" 2>&1 | tee "$logfile"
  else
    "${cmd[@]}" > "$logfile" 2>&1
  fi
  echo "[$(date)] finished ${bench}; log=${logfile}"
}

PYTHON_BIN="${PYTHON_BIN:-python}"

IFS=',' read -r -a BENCH_ARRAY <<< "$BENCHES"
for bench in "${BENCH_ARRAY[@]}"; do
  bench="$(echo "$bench" | xargs)"
  case "$bench" in
    toolhop)
      run_bench "ToolHop" "toolhop" "toolhop_test_full" --infile "$TOOLHOP_INFILE"
      ;;
    tmdb|restbench_tmdb)
      run_bench "RestBench-TMDB" "restbench_tmdb" "restbench_tmdb_full"
      ;;
    api_bank|apibank)
      run_bench "API-Bank" "api_bank" "api_bank_full"
      ;;
    "")
      ;;
    *)
      echo "Unsupported bench: $bench" >&2
      exit 2
      ;;
  esac
done

echo "[$(date)] all requested benches finished."
echo "Run root: $RUN_ROOT"
