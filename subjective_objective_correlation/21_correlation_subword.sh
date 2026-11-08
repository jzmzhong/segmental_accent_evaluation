#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

export PYTHONUNBUFFERED=1
exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/21_correlation_subword.py" "$@"
