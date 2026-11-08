#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# Download every metric's models by default; forward --models and --model-dir.
# This downloads files only and needs no GPU allocation.
exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/model_setup.py" "$@"
