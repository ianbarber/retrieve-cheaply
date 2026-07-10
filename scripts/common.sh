#!/usr/bin/env bash
# Shared, repository-relative setup for experiment drivers.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[1]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"
PY="${PYTHON:-python3}"
