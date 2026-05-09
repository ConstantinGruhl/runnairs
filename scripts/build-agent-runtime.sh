#!/usr/bin/env bash
# Build the agent runtime base image. Per-agent images are built on top of
# this in Phase 5+.
set -euo pipefail
cd "$(dirname "$0")/.."
docker build -f agent-runtime/Dockerfile -t platform/agent-runtime:latest .
