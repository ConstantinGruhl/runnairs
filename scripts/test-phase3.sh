#!/usr/bin/env bash
# Phase 3 verification: SDK -> tool gateway -> audit log
#
# Spins up a one-off agent-runtime container, mounts the SDK, calls
# tools.llm.complete with a freshly minted run token, and confirms an
# audit_log row was written. Works without an OpenAI key (stub backend).
set -euo pipefail
cd "$(dirname "$0")/.."

NETWORK=agent-platform_default

echo "==> [1/4] Mint run token"
TOKEN_JSON=$(docker compose exec -T control-plane python -m app.cli mint-run-token \
  --tenant-email admin@demo.local \
  --user-email user@demo.local \
  --tool llm.complete \
  --secret "OPENAI_API_KEY:workspace")
RUN_TOKEN=$(echo "$TOKEN_JSON" | python -c "import sys,json;print(json.load(sys.stdin)['run_token'])")
echo "    token len=${#RUN_TOKEN}"

echo "==> [2/4] Call tools.llm.complete from a one-off agent-runtime container"
docker run --rm \
  --network "$NETWORK" \
  -e RUN_TOKEN="$RUN_TOKEN" \
  -e TOOL_GATEWAY_URL=http://tool-gateway:8001 \
  --entrypoint python \
  platform/agent-runtime:latest \
  -c "
from platform_sdk import tools
res = tools.llm.complete(
    model='gpt-4o-mini',
    prompt='Say hi to the platform in 5 words.',
)
print(f'  backend tokens={res.tokens_used} cost_usd={res.cost_usd:.6f}')
print(f'  text: {res.text!r}')
"

echo "==> [3/4] Latest audit_log row"
docker compose exec -T postgres psql -U platform -d platform -c \
  "SELECT tool_name, status, duration_ms, cost_usd, result_summary,
          left(args_sanitized_json::text, 120) AS args_preview
   FROM audit_log ORDER BY created_at DESC LIMIT 1;"

echo "==> [4/4] Done."
