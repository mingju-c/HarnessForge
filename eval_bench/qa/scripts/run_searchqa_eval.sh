#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT=${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}
WORKSPACE=${HARNESSFORGE_WORKSPACE:-$REPO_ROOT/HarnessForge_4B}
QA_ROOT="$REPO_ROOT/eval_bench/qa"
if [ -f "$QA_ROOT/.env" ]; then
  set -a
  source "$QA_ROOT/.env"
  set +a
fi
export MIXED_SEARCHQA_RETRIEVE_DIR=${MIXED_SEARCHQA_RETRIEVE_DIR:-"$QA_ROOT/retrieve_data"}
DATASET=${DATASET:-all}
DATA_FILE=${DATA_FILE:-"$QA_ROOT/data/${DATASET}.jsonl"}
PYTHON_BIN=${PYTHON_BIN:-python}
if [ ! -s "$DATA_FILE" ]; then
  echo "Missing or empty QA data file: $DATA_FILE" >&2
  echo "Build it with: $PYTHON_BIN $QA_ROOT/scripts/build_searchqa_eval.py --allow-missing" >&2
  exit 2
fi
exec "$PYTHON_BIN" "$WORKSPACE/run_infer.py" --benchmark mixeddata --infile "$DATA_FILE" "$@"
