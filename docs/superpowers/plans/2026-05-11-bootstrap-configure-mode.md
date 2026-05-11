# Bootstrap Configure Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or equivalent task-by-task execution. This plan is written to satisfy Phase 2 of `2026-05-11-production-readiness-execution-checklist.md` before any bootstrap/configure-mode product code lands.

**Goal:** Ensure a fresh self-hosted instance cannot be used normally until an operator has created the first admin, confirmed core runtime/security prerequisites, and completed a first-run configure flow that can resume safely after reloads.

**Architecture:** Add a small instance-level settings store plus a bootstrap service that derives a single source of truth for configure-mode state. During bootstrap, allow only health checks, login, and bootstrap APIs; block standard admin/dev/user APIs until setup completes. Reuse the existing `Tenant` + `User` models by creating the first tenant/admin during setup and by marking the demo seed path as already bootstrapped.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Next.js 14 app router, local-storage auth session (existing), pytest

---

## File Structure

**Create:**
- `services/control-plane/app/models/instance_setting.py`
- `services/control-plane/app/services/bootstrap_service.py`
- `services/control-plane/app/api/bootstrap.py`
- `services/control-plane/app/schemas/bootstrap.py`
- `services/control-plane/alembic/versions/0005_instance_bootstrap.py`
- `tests/unit/test_bootstrap_service.py`
- `frontend/app/setup/page.tsx`
- `frontend/components/BootstrapSetupWizard.tsx`
- `frontend/lib/bootstrap.ts`

**Modify:**
- `services/control-plane/app/models/__init__.py`
- `services/control-plane/app/main.py`
- `services/control-plane/app/api/auth.py`
- `services/control-plane/app/core/dependencies.py`
- `services/control-plane/app/seed.py`
- `frontend/app/page.tsx`
- `frontend/app/login/page.tsx`
- `frontend/components/RoleGuard.tsx`
- `frontend/lib/types.ts`
- `README.md`

## Assumptions Locked For This Plan

- Keep the existing single-tenant behavior by creating one bootstrap tenant and one initial admin; do not attempt multi-tenant setup UX in this phase.
- Keep existing JWT/local-storage auth for now, but restrict it during bootstrap so only the bootstrap admin can authenticate/resume setup before unlock.
- Treat `JWT_SECRET` and `PLATFORM_SECRETS_KEY` as operator-managed environment configuration. The setup wizard validates them; it does not write environment files.
- Treat `notification_from_email` as the minimum required mail/notification default stored in the database for this phase.

## 2026-05-11 Implementation Note

- Current shipped coverage is still unit-test heavy; fresh-instance bootstrap, login-resume, and route-lockout behavior have not yet been proven with app-level integration tests.
- Configure mode currently hard-codes `auth_mode` to `built_in`; the first-run wizard does not yet expose IAM mode selection or provider setup.
- The setup UI shows runtime check status and blocking reasons, but there is not yet an automated browser or API first-run certification flow for a brand-new deployment.

## Task 1: Add Instance-Level Bootstrap State And Policy Helpers

**Files:**
- Create: `services/control-plane/app/models/instance_setting.py`
- Create: `services/control-plane/app/services/bootstrap_service.py`
- Create: `services/control-plane/app/schemas/bootstrap.py`
- Create: `services/control-plane/alembic/versions/0005_instance_bootstrap.py`
- Create: `tests/unit/test_bootstrap_service.py`
- Modify: `services/control-plane/app/models/__init__.py`

- [ ] Add an `instance_setting` table keyed by unique string `key` with `value_json`, `created_at`, and `updated_at`.
- [ ] Store bootstrap progress under a canonical bootstrap key instead of scattering state across unrelated tables.
- [ ] Implement bootstrap helpers that answer:
  - does this instance still require bootstrap?
  - has the first admin been created?
  - which tenant/admin/email/name/notification defaults are currently stored?
  - are the required runtime checks green right now?
- [ ] Runtime checks must include:
  - strong `JWT_SECRET` already enforced by service config
  - non-empty `PLATFORM_SECRETS_KEY`
  - database connectivity from the control plane
- [ ] Unit tests must cover:
  - fresh instance returns bootstrap-required state
  - admin-created-but-incomplete instance returns resumable partial state
  - complete state flips bootstrap-required to false
  - second anonymous bootstrap initialization is blocked after the first admin exists

**Verification**

Run:

```powershell
$env:PYTHONPATH="services/control-plane;packages/platform_sdk;packages/platform_cli"
py -3.13 -m pytest tests/unit/test_bootstrap_service.py -q
```

Expected: PASS

## Task 2: Add Bootstrap APIs And Backend Gating

**Files:**
- Create: `services/control-plane/app/api/bootstrap.py`
- Modify: `services/control-plane/app/main.py`
- Modify: `services/control-plane/app/api/auth.py`
- Modify: `services/control-plane/app/core/dependencies.py`

- [ ] Add public bootstrap endpoints:
  - `GET /bootstrap/state`
  - `POST /bootstrap/initialize`
- [ ] Add admin-authenticated bootstrap endpoints for incomplete instances:
  - `PUT /bootstrap/configure`
  - `POST /bootstrap/complete`
- [ ] `POST /bootstrap/initialize` must:
  - create the first tenant if missing
  - create the first admin if missing
  - persist workspace name, admin email, auth mode (`built_in`), and notification defaults
  - return a normal access token + user payload so the admin can resume setup after reload
- [ ] `POST /bootstrap/complete` must refuse completion until required checks pass and required fields exist.
- [ ] Add request-time bootstrap gating in `main.py`:
  - allow `/health`
  - allow `/bootstrap/*`
  - allow `/auth/login` and `/auth/me`
  - block normal admin/dev/app APIs with a bootstrap-incomplete error until completion
- [ ] Update login behavior so, during incomplete bootstrap, only the configured bootstrap admin can authenticate.

**Verification**

Run:

```powershell
$env:PYTHONPATH="services/control-plane;packages/platform_sdk;packages/platform_cli"
py -3.13 -m pytest tests/unit/test_bootstrap_service.py tests/unit/test_runtime_security_settings.py -q
```

Expected: PASS

## Task 3: Add Frontend Setup Route And Route Guards

**Files:**
- Create: `frontend/app/setup/page.tsx`
- Create: `frontend/components/BootstrapSetupWizard.tsx`
- Create: `frontend/lib/bootstrap.ts`
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/app/login/page.tsx`
- Modify: `frontend/components/RoleGuard.tsx`
- Modify: `frontend/lib/types.ts`

- [ ] Add a `/setup` route that:
  - fetches bootstrap state
  - renders first-run setup when no admin exists
  - renders resumable configure mode when bootstrap is partial
  - redirects to `/login` or the role landing page once bootstrap is complete
- [ ] Update `/` to redirect to `/setup` when bootstrap is required.
- [ ] Update `/login` to redirect to `/setup` while bootstrap remains incomplete.
- [ ] Update `RoleGuard` so authenticated users cannot access normal app/admin/dev routes until bootstrap is complete.
- [ ] Setup UI must capture:
  - workspace name
  - admin email
  - admin password
  - notification-from email
- [ ] Setup UI must display current system checks and explain which ones block completion.

**Verification**

Run:

```bash
npm --prefix frontend run build
```

Expected: PASS, including `/setup` and route-gating changes

## Task 4: Preserve Demo/Seeded Flows And Document The New First-Run Story

**Files:**
- Modify: `services/control-plane/app/seed.py`
- Modify: `README.md`

- [ ] Make `python -m app.seed` mark the instance as bootstrapped so existing local demo workflows still work after seeding.
- [ ] Document the difference between:
  - fresh self-hosted bootstrap flow
  - optional demo seeding for local development
- [ ] Keep current demo credentials documented only as a post-seed path, not as the default first-run experience.

**Verification**

Run:

```bash
npm --prefix frontend run build
docker compose -f docker-compose.yml -f docker-compose.prod.yml config
```

Expected: PASS

## Phase 2 Final Verification

Run:

```powershell
$env:PYTHONPATH="services/control-plane;packages/platform_sdk;packages/platform_cli"
py -3.13 -m pytest tests/unit/test_bootstrap_service.py tests/unit/test_runtime_security_settings.py tests/unit/test_schedule_service.py -q
npm --prefix frontend run build
docker compose -f docker-compose.yml -f docker-compose.prod.yml config
```

Manual smoke once the stack is running:

- fresh instance reports bootstrap-required from `GET /bootstrap/state`
- `/` and `/login` route into `/setup` until completion
- first admin creation succeeds once, then anonymous re-initialization is blocked
- partial setup survives reload because the bootstrap admin can log back in and resume
- successful completion unlocks normal login/routes without DB edits

## Commit Boundary

- Commit 1: bootstrap state model, migration, and service tests
- Commit 2: bootstrap API + backend gating
- Commit 3: setup UI, route gating, seed/docs updates
