#!/usr/bin/env bash
# Run all tests: agent unit tests under examples/, plus the integration
# happy-path against the running compose stack.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> agent unit tests (examples/)"
MSYS_NO_PATHCONV=1 docker run --rm \
  -v "$(pwd -W 2>/dev/null || pwd)/packages/platform_sdk:/sdk" \
  -v "$(pwd -W 2>/dev/null || pwd)/examples:/examples:ro" \
  python:3.12-slim \
  bash -c "pip install --quiet /sdk pytest && \
    cd /examples/hello-world && PYTHONPATH=. pytest tests/ -q -p no:cacheprovider && \
    cd /examples/weekly-summary && PYTHONPATH=. pytest tests/ -q -p no:cacheprovider"

echo "==> integration happy path"
python -m pytest tests/integration -q
