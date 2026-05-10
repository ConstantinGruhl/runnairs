#!/usr/bin/env bash
# Build all example agent images. Requires platform/agent-runtime first.
set -euo pipefail
cd "$(dirname "$0")/.."

for agent in hello-world weekly-summary inbox-triage customer-briefing; do
  echo "==> building platform/$agent:v1"
  docker build -t "platform/$agent:v1" "examples/$agent"
done
