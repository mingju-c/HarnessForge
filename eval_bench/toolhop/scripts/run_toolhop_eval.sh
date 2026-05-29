#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT=${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}
WORKSPACE=${HARNESSFORGE_WORKSPACE:-$REPO_ROOT/HarnessForge_4B}
PYTHON_BIN=${PYTHON_BIN:-python}
INFILE=${TOOLHOP_INFILE:-test}
exec "$PYTHON_BIN" "$WORKSPACE/run_infer.py" --benchmark toolhop --infile "$INFILE" "$@"
