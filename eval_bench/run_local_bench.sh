#!/usr/bin/env bash
set -euo pipefail
BENCH=${1:-}
shift || true
case "$BENCH" in
  qa|searchqa) exec bash eval_bench/qa/scripts/run_searchqa_eval.sh "$@" ;;
  tau|tau-bench|taubench) exec bash eval_bench/tau-bench/scripts/run_taubench_eval.sh "$@" ;;
  toolhop) exec bash eval_bench/toolhop/scripts/run_toolhop_eval.sh "$@" ;;
  api-bank|api_bank) exec bash eval_bench/api-bank/scripts/run_api_bank_eval.sh "$@" ;;
  tmdb|restbench_tmdb) exec bash eval_bench/tmdb/scripts/run_tmdb_eval.sh "$@" ;;
  *) echo "Usage: bash eval_bench/run_local_bench.sh {qa|tau-bench|toolhop|api-bank|tmdb} [run_infer args...]" >&2; exit 2 ;;
esac
