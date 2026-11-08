#!/usr/bin/env bash
#SBATCH --output=slurm-%j.log
set -euo pipefail

# Slurm runs a spool copy; submit from this script's directory.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -f "$SCRIPT_DIR/21_correlation_subword.py" ]]; then
    SCRIPT_DIR="${SLURM_SUBMIT_DIR:-$PWD}"
fi

export PYTHONUNBUFFERED=1
exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/21_correlation_subword.py" "$@"
