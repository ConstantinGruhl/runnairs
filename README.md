# Enterprise AI Agent Platform — Local Prototype

A platform where admins govern, developers build, and end users run AI agents
with isolated execution, scoped secrets, audited tool calls, and human approvals.

This is a local prototype built in phases. The current phase is recorded below.

## Status

- [x] **Phase 0** — Scaffold (compose stack, health checks)
- [x] **Phase 1** — Auth + data model
- [x] **Phase 2** — Secret store
- [x] **Phase 3** — Agent SDK + tool gateway (LLM)
- [x] **Phase 4** — Execution backend (Docker)
- [x] **Phase 5** — Agent deploy + CLI
- [x] **Phase 6** — Catalog + run UI
- [x] **Phase 7** — Approvals
- [x] **Phase 8** — Remaining tools + sample agents
- [x] **Phase 9** — Feedback loop
- [ ] **Phase 10** — Scheduling
- [ ] **Phase 11** — Platform skill + tests
- [ ] **Phase 12** — README + demo script

## Quickstart (Phase 0)

```bash
cp .env.example .env
# Generate a Fernet key for PLATFORM_SECRETS_KEY (used in later phases):
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Paste the output into .env

docker compose up --build
```

When the stack is up:

| Service        | URL                     | Notes                          |
|----------------|-------------------------|--------------------------------|
| Frontend       | http://localhost:3000   | Login page only at this phase  |
| Control plane  | http://localhost:8000   | `/health` returns `{ok: true}` |
| Tool gateway   | http://localhost:8001   | `/health` returns `{ok: true}` |
| Mock CRM       | http://localhost:8080   | `/customers`, `/health`        |
| MailHog UI     | http://localhost:8025   | Inbox for outgoing email       |
| Postgres       | localhost:5432          | Control plane DB               |
| Sample data DB | localhost:5433          | Demo CRM data                  |
| Redis          | localhost:6379          | Job queue                      |

`docker compose ps` should show all services healthy.

## Repo layout

```
packages/        Python packages: platform_sdk (agent-facing), platform_cli (dev CLI)
services/        Long-running services: control-plane, tool-gateway, mock-crm
frontend/        Next.js app (admin / dev / user catalog)
agent-runtime/   Base Docker image for deployed agents
examples/        Sample agents (weekly-summary, inbox-triage, customer-briefing)
skills/          Claude Code skill that teaches how to build agents on this platform
tests/           Unit + integration tests
scripts/         Seed and demo scripts
```

## Architecture (high level)

```
                   ┌──────────────┐
                   │   Frontend   │  Next.js
                   └──────┬───────┘
                          │ HTTPS (JWT)
                   ┌──────▼───────┐        ┌────────────┐
                   │ Control plane│◄──────►│  Postgres  │
                   │   FastAPI    │        └────────────┘
                   └──────┬───────┘
                          │ enqueues
                   ┌──────▼───────┐
                   │   Worker     │  RQ
                   └──────┬───────┘
                          │ start_run
                   ┌──────▼─────────┐
                   │ ExecutionBackend│ (Docker today, K8s tomorrow)
                   └──────┬──────────┘
                          │ runs
                   ┌──────▼──────┐         ┌───────────────┐
                   │   Agent     │────────►│ Tool gateway  │── audit log
                   │  container  │  HTTP   │   FastAPI     │── secrets
                   └─────────────┘         └───────┬───────┘
                                                   │
                                ┌──────────────────┼─────────────────┐
                                ▼                  ▼                 ▼
                            LLM APIs          MailHog SMTP      Mock CRM / sample DB
```

## Seeding

After `docker compose up`, seed the demo workspace:

```bash
./scripts/seed.sh
```

This creates one tenant ("Demo Workspace") and three users:

| Email              | Password     | Role      |
|--------------------|--------------|-----------|
| admin@demo.local   | demo-admin   | admin     |
| dev@demo.local     | demo-dev     | developer |
| user@demo.local    | demo-user    | user      |

The script is idempotent — safe to re-run.

## Workspace secrets

Workspace secrets are encrypted at rest with Fernet. The encryption key
comes from `PLATFORM_SECRETS_KEY` in `.env`. If unset, a deterministic
dev key is derived from `JWT_SECRET` (loud warning logged) — fine for
local play, never for anything real.

Generate a real key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Admin UI at <http://localhost:3000/admin/secrets> after signing in as
`admin@demo.local`.

## Agent SDK + tool gateway

The platform has a working `tools.llm.complete` end-to-end:

```bash
./scripts/build-agent-runtime.sh   # one-time, builds platform/agent-runtime:latest
./scripts/test-phase3.sh           # mints a run token, calls the SDK, prints the audit row
```

Without `OPENAI_API_KEY` configured for the tenant, the gateway falls
back to a deterministic stub backend (the demo runs without keys). With
a key configured via the admin secrets UI, the gateway calls OpenAI for
real and reports actual token usage and cost.

## Run lifecycle (hello-world end-to-end)

```bash
./scripts/build-agent-runtime.sh   # base image with platform_sdk
./scripts/build-hello-world.sh     # examples/hello-world image
./scripts/seed.sh                  # tenant + users + hello-world Agent row

# Trigger a run (any logged-in user):
curl -X POST http://localhost:8000/runs \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"agent_slug":"hello-world","inputs":{"greeting":"Hi"}}'

# Poll status:
curl http://localhost:8000/runs/<run_id> -H "Authorization: Bearer $TOKEN"
```

Each run boots a fresh container with the platform's invariants in
place: read-only root, tmpfs at `/tmp`, no privileged, all caps
dropped, mem/cpu limits from the manifest, attached only to the
internal `agent-egress` network so the tool gateway is the only peer
the agent can reach. Verified: external HTTPS and DNS lookups from
inside an agent container fail; `tool-gateway:8001/health` works.

## Developer CLI

```bash
pip install -e packages/platform_cli
platform-cli login --email dev@demo.local --api-url http://localhost:8000
platform-cli init my-agent
# edit my-agent/agent.yaml + my-agent/main.py
platform-cli deploy ./my-agent
```

`deploy` zips the directory, uploads to `POST /dev/agents/deploy`, and the
control plane validates the manifest, builds an image tagged
`agent-<uuid>:v<n>` from `platform/agent-runtime` + the agent code, and
creates a draft `AgentVersion` row. Admins approve it via
`POST /admin/agents/<slug>/approve` (UI lands in Phase 6) before end
users can run it.

## Approvals + email

`weekly-summary` now demonstrates the full pause-and-approve loop:

1. End user runs the agent.
2. After the LLM summary, the agent calls `ctx.request_approval(action="email.send", ...)`.
3. Run status flips to `awaiting_approval`. The run detail page shows
   the pending approval inline.
4. An admin clicks Approve (or hits `POST /admin/approvals/{id}/decide`).
5. The agent's long-poll returns, the agent calls `tools.email.send`,
   which the gateway accepts because there's now an approved approval
   for the `email.send` action.
6. Email lands in MailHog at <http://localhost:8025>.

If denied (or timed out), the agent returns without calling
`email.send`. If the agent tries to call an approval-gated tool
without an approved approval, the gateway returns 403.

## Sample agents

`scripts/build-examples.sh` builds all four images
(`hello-world`, `weekly-summary`, `inbox-triage`, `customer-briefing`).
Deploy them with `platform-cli deploy ./examples/<slug>`. The seed
script ships only the `hello-world` row; the rest land via deploy.

| Agent | Demonstrates |
|---|---|
| weekly-summary | postgres.query + llm + approval + email |
| inbox-triage | inbox.list (gateway-side mock) + user-scope MAILBOX_TOKEN gating |
| customer-briefing | postgres + http with `permissions.http_allowlist` against the mock CRM |

Connect a user-scope secret from the catalog page: open an agent that
declares one (e.g. `inbox-triage`), click Connect under the new
**Connect your accounts** card, paste a token. Run history shows the
explicit failure mode if a user runs without connecting first.

## Known limitations (will resolve in later phases)

- Anthropic + other LLM providers can be plugged into the gateway
  alongside OpenAI; only OpenAI is wired today.
- Cron-based scheduling lands in Phase 10.
