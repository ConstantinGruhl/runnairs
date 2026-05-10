#!/usr/bin/env bash
# Apply the sample-data init scripts against the running sample_data container.
# Useful when the volume already has data (compose's init scripts only run
# on first boot).
set -euo pipefail
cd "$(dirname "$0")/.."
for sql in services/sample-data-init/*.sql; do
  echo "==> applying $sql"
  docker compose exec -T sample_data psql -U sample -d sample < "$sql"
done
