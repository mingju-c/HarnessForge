#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT=${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}
WORKSPACE=${HARNESSFORGE_WORKSPACE:-$REPO_ROOT/HarnessForge_4B}
TMDB_ROOT="$REPO_ROOT/eval_bench/tmdb"
if [ -f "$TMDB_ROOT/.env" ]; then
  set -a
  source "$TMDB_ROOT/.env"
  set +a
fi
PYTHON_BIN=${PYTHON_BIN:-python}
exec "$PYTHON_BIN" "$WORKSPACE/run_infer.py" --benchmark restbench_tmdb "$@"
