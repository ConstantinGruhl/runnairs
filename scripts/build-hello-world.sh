#!/usr/bin/env bash
# Build the hello-world example agent image. Requires the agent-runtime
# base image to exist (run scripts/build-agent-runtime.sh first).
set -euo pipefail
cd "$(dirname "$0")/../examples/hello-world"
docker build -t platform/hello-world:v1 .
