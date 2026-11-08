#!/usr/bin/env bash
set -euo pipefail

# Slurm runs a spool copy; run_l40s_cdt should be called from this directory.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -f "$SCRIPT_DIR/12_extract_features.py" ]]; then
    SCRIPT_DIR="${SLURM_SUBMIT_DIR:-$PWD}"
fi

export PYTHONUNBUFFERED=1
exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/12_extract_features.py" \
    --device cuda:0 --gpu 0 "$@"
