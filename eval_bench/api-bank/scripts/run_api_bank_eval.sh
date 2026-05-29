#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT=${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}
WORKSPACE=${HARNESSFORGE_WORKSPACE:-$REPO_ROOT/HarnessForge_4B}
API_ROOT="$REPO_ROOT/eval_bench/api-bank"
if [ -f "$API_ROOT/.env" ]; then
  set -a
  source "$API_ROOT/.env"
  set +a
fi
export API_BANK_APIS_DIR=${API_BANK_APIS_DIR:-"$API_ROOT/apis"}
export API_BANK_DATABASE_DIR=${API_BANK_DATABASE_DIR:-"$API_ROOT/init_database"}
PYTHON_BIN=${PYTHON_BIN:-python}
BENCHMARK=${BENCHMARK:-api_bank}
exec "$PYTHON_BIN" "$WORKSPACE/run_infer.py" --benchmark "$BENCHMARK" "$@"
