#!/usr/bin/env bash
# Guided end-to-end demo from §16 of the spec.
#
# Walks through:
#   dev   → deploy weekly-summary
#   admin → approve the version
#   user  → kick off a run, hits awaiting_approval
#   admin → approve the email send
#   user  → run finishes, email lands in MailHog, user leaves feedback
#   dev   → sees the feedback in the dashboard
#
# Assumes: compose stack is up, ./scripts/seed.sh has run, the
# agent-runtime image is built. Re-runnable.
set -euo pipefail
cd "$(dirname "$0")/.."

API="http://localhost:8000"
MAILHOG_API="http://localhost:8025"
CYAN="\033[36m"; YELLOW="\033[33m"; GREEN="\033[32m"; DIM="\033[2m"; RESET="\033[0m"

bullet() { printf "${CYAN}==>${RESET} %s\n" "$1"; }
step()   { printf "\n${YELLOW}── %s ──${RESET}\n" "$1"; }
say()    { printf "    %s\n" "$1"; }

login() {
  local email="$1" password="$2"
  curl -s -X POST "$API/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$email\",\"password\":\"$password\"}" \
    | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])"
}

step "1) Health check"
if ! curl -sf "$API/health" >/dev/null; then
  echo "control-plane is not reachable at $API. Run \`docker compose up\` first." >&2
  exit 1
fi
say "control-plane: ok"
say "tool-gateway: $(curl -s http://localhost:8001/health | python -c "import sys,json;print('ok' if json.load(sys.stdin)['ok'] else 'down')")"
say "MailHog: $(curl -s -o /dev/null -w '%{http_code}' http://localhost:8025)"

step "2) Login as dev@demo.local"
DEV_TOKEN=$(login "dev@demo.local" "demo-dev")
say "got token (${#DEV_TOKEN} chars)"

step "3) Deploy ./examples/weekly-summary via platform-cli"
DEPLOY=$(MSYS_NO_PATHCONV=1 docker run --rm \
  --network agent-platform_default \
  -v "$(pwd -W 2>/dev/null || pwd)/packages/platform_cli:/cli" \
  -v "$(pwd -W 2>/dev/null || pwd)/examples/weekly-summary:/agent:ro" \
  -e PLATFORM_CLI_CONFIG=/tmp/cli.json \
  python:3.12-slim \
  bash -c "pip install --quiet /cli && \
    platform-cli login --email dev@demo.local --api-url http://control-plane:8000 --password demo-dev > /dev/null && \
    platform-cli deploy /agent" 2>&1 | tail -2)
echo "$DEPLOY" | sed 's/^/    /'

step "4) Login as admin@demo.local and approve the version"
ADMIN_TOKEN=$(login "admin@demo.local" "demo-admin")
APPROVE=$(curl -s -X POST "$API/admin/agents/weekly-summary/approve" -H "Authorization: Bearer $ADMIN_TOKEN")
say "approved: $(echo "$APPROVE" | python -c "import sys,json;d=json.load(sys.stdin);print(f'version={d[\"version\"]} status={d[\"status\"]}')")"

step "5) Clear MailHog so we can verify the email later"
curl -s -X DELETE "$MAILHOG_API/api/v1/messages" >/dev/null
say "MailHog inbox cleared"

step "6) Login as user@demo.local and start a weekly-summary run"
USER_TOKEN=$(login "user@demo.local" "demo-user")
RUN=$(curl -s -X POST "$API/runs" \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"agent_slug":"weekly-summary","inputs":{"region":"EMEA","recipient_email":"sales-emea@example.com"}}')
RUN_ID=$(echo "$RUN" | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
say "run_id=$RUN_ID"
say "watch: $API/runs/$RUN_ID  (or http://localhost:3000/app/runs/$RUN_ID)"

step "7) Wait for the run to pause at awaiting_approval"
for i in $(seq 1 60); do
  STATUS=$(curl -s "$API/runs/$RUN_ID" -H "Authorization: Bearer $USER_TOKEN" | python -c "import sys,json;print(json.load(sys.stdin)['status'])")
  if [ "$STATUS" = "awaiting_approval" ]; then
    say "status=awaiting_approval after ${i}s"
    break
  fi
  if [ "$STATUS" = "succeeded" ] || [ "$STATUS" = "failed" ]; then
    say "unexpected status=$STATUS — agent may not require approval"
    break
  fi
  sleep 1
done

step "8) Admin approves the pending email send"
APPROVAL_ID=$(curl -s "$API/runs/$RUN_ID/approvals" -H "Authorization: Bearer $USER_TOKEN" \
  | python -c "import sys,json; r=json.load(sys.stdin); pending=[a for a in r if a['status']=='pending']; print(pending[0]['id'] if pending else '')")
if [ -z "$APPROVAL_ID" ]; then
  say "no pending approval — agent didn't pause this run; skipping approval step"
else
  say "approval_id=$APPROVAL_ID"
  curl -s -X POST "$API/admin/approvals/$APPROVAL_ID/decide" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"decision":"approved"}' >/dev/null
  say "decision=approved"
fi

step "9) Wait for the run to finish"
for i in $(seq 1 60); do
  STATUS=$(curl -s "$API/runs/$RUN_ID" -H "Authorization: Bearer $USER_TOKEN" | python -c "import sys,json;print(json.load(sys.stdin)['status'])")
  if [ "$STATUS" = "succeeded" ] || [ "$STATUS" = "failed" ]; then break; fi
  sleep 1
done
RESULT=$(curl -s "$API/runs/$RUN_ID" -H "Authorization: Bearer $USER_TOKEN")
echo "$RESULT" | python -c "
import sys, json
r = json.load(sys.stdin)
res = r.get('result_json') or {}
print(f'    status={r[\"status\"]}')
print(f'    email_sent={res.get(\"email_sent\")} approval_status={res.get(\"approval_status\")}')
print(f'    rows={res.get(\"row_count\")} tokens={res.get(\"tokens\")} backend={res.get(\"backend\")}')
"

step "10) Check MailHog for the email"
INBOX=$(curl -s "$MAILHOG_API/api/v2/messages")
echo "$INBOX" | python -c "
import sys, json
inbox = json.load(sys.stdin)
print(f'    inbox total = {inbox[\"total\"]}')
for m in inbox['items'][:3]:
    to = f\"{m['To'][0]['Mailbox']}@{m['To'][0]['Domain']}\"
    subj = m['Content']['Headers'].get('Subject', [''])[0]
    print(f'    → {to}   subject={subj!r}')
"

step "11) User leaves feedback on the run"
curl -s -X POST "$API/runs/$RUN_ID/feedback" \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"rating":"up","comment":"Bullets matched the data nicely."}' \
  | python -c "import sys,json;d=json.load(sys.stdin);print(f'    rating={d[\"rating\"]} comment={d[\"comment\"]!r}')"

step "12) Dev sees the feedback in the dashboard"
curl -s "$API/dev/agents/weekly-summary/feedback" -H "Authorization: Bearer $DEV_TOKEN" \
  | python -c "
import sys, json
d = json.load(sys.stdin)
print(f'    👍 {d[\"up_count\"]}   👎 {d[\"down_count\"]}   {d[\"total_runs_with_feedback\"]} run(s) rated')
for item in d['items'][:3]:
    print(f'    · run {item[\"run_id\"][:8]}…  {item[\"rating\"]}  {item[\"comment\"]!r}')
"

printf "\n${GREEN}done.${RESET}\n"
say "explore the UI:    http://localhost:3000"
say "MailHog inbox:     http://localhost:8025"
say "this run detail:   http://localhost:3000/app/runs/$RUN_ID"
