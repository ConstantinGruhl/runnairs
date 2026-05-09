# Enterprise AI Agent Platform — Local Prototype

A platform where admins govern, developers build, and end users run AI agents
with isolated execution, scoped secrets, audited tool calls, and human approvals.

This is a local prototype built in phases. The current phase is recorded below.

## Status

- [x] **Phase 0** — Scaffold (compose stack, health checks)
- [x] **Phase 1** — Auth + data model
- [x] **Phase 2** — Secret store
- [ ] **Phase 3** — Agent SDK + tool gateway (LLM)
- [ ] **Phase 4** — Execution backend (Docker)
- [ ] **Phase 5** — Agent deploy + CLI
- [ ] **Phase 6** — Catalog + run UI
- [ ] **Phase 7** — Approvals
- [ ] **Phase 8** — Remaining tools + sample agents
- [ ] **Phase 9** — Feedback loop
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

## Known limitations (will resolve in later phases)

- No real agent execution yet (Phase 4).
- `agent-runtime` image is a placeholder (Phase 4).
- User-scope secrets (per-user OAuth-style tokens) land in Phase 8.
