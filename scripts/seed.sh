#!/usr/bin/env bash
# Seed the demo tenant + admin/dev/user accounts.
# Requires the compose stack to be running.
set -e
docker compose exec -T control-plane python -m app.seed
