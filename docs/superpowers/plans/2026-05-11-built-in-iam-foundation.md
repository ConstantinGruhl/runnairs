# Built-In IAM Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to execute this plan task by task. This plan is the dedicated child plan required by Task 2 of `2026-05-11-production-readiness-gap-closure.md`.

**Goal:** Turn the current bootstrap-era local login into a supportable built-in IAM foundation for self-hosted deployments: the operator must explicitly choose built-in IAM during setup, normal browser sessions must stop depending on `localStorage` bearer tokens, admins must be able to manage workspace users without database edits, and the platform must provide a documented and tested recovery path for the bootstrap admin.

**Architecture:** Keep JWT as the session artifact for now, but move browser auth to same-origin `HttpOnly` cookies while preserving bearer-token compatibility for API clients and the CLI. Extend the existing `User` model with lifecycle and revocation fields instead of introducing a separate identity model in this phase. Persist bootstrap `auth_mode` explicitly and expose it through setup UI so the instance is prepared for future OIDC work without shipping OIDC yet.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Next.js 14 app router, browser cookie sessions, pytest with app-level PostgreSQL-backed integration coverage

---

## Assumptions Locked For This Plan

- Built-in IAM is the only shippable auth provider in this phase; OIDC appears in setup only as future-facing copy or disabled selection state if needed, but no external-provider code lands here.
- Browser sessions should use `HttpOnly`, `SameSite=Lax` cookies on the same-origin frontend proxy. The login API may still return a bearer token for compatibility, but the frontend must stop storing it in `localStorage`.
- User lifecycle in this phase means: create user, set role, disable or re-enable user, generate a password reset path, and recover the bootstrap admin through a one-time recovery code flow.
- Password policy should be enforced centrally and reused by bootstrap admin creation, admin-created users, password reset, and recovery completion.
- This phase should update operator-facing docs for built-in IAM and recovery, even though broader self-hosting docs will be revisited again in the final certification task.

## File Structure

**Create:**
- `services/control-plane/app/services/auth_service.py`
- `services/control-plane/app/services/user_management_service.py`
- `services/control-plane/app/schemas/admin_users.py`
- `services/control-plane/alembic/versions/0006_built_in_iam_foundation.py`
- `tests/unit/test_auth_service.py`
- `tests/integration/test_built_in_iam_bootstrap.py`
- `tests/integration/test_auth_sessions.py`
- `tests/integration/test_admin_user_management.py`
- `frontend/app/admin/users/page.tsx`
- `frontend/components/UserManagementPanel.tsx`

**Modify:**
- `services/control-plane/app/models/user.py`
- `services/control-plane/app/models/__init__.py`
- `services/control-plane/app/schemas/auth.py`
- `services/control-plane/app/schemas/bootstrap.py`
- `services/control-plane/app/services/bootstrap_service.py`
- `services/control-plane/app/api/auth.py`
- `services/control-plane/app/api/bootstrap.py`
- `services/control-plane/app/api/admin.py`
- `services/control-plane/app/core/security.py`
- `services/control-plane/app/core/dependencies.py`
- `tests/unit/test_bootstrap_service.py`
- `frontend/app/setup/page.tsx`
- `frontend/app/login/page.tsx`
- `frontend/app/admin/layout.tsx`
- `frontend/components/AppShell.tsx`
- `frontend/components/BootstrapSetupWizard.tsx`
- `frontend/components/RoleGuard.tsx`
- `frontend/components/PlatformDocs.tsx`
- `frontend/lib/api.ts`
- `frontend/lib/auth.ts`
- `frontend/lib/types.ts`
- `docs/self-hosting.md`

## Task 1: Persist Built-In IAM Choice And Extend The User Auth Model

**Files:**
- Modify: `services/control-plane/app/models/user.py`
- Modify: `services/control-plane/app/models/__init__.py`
- Modify: `services/control-plane/app/schemas/bootstrap.py`
- Modify: `services/control-plane/app/services/bootstrap_service.py`
- Modify: `services/control-plane/app/api/bootstrap.py`
- Create: `services/control-plane/alembic/versions/0006_built_in_iam_foundation.py`
- Modify: `tests/unit/test_bootstrap_service.py`

- [ ] Extend `User` with the minimum built-in IAM lifecycle fields:
  - `status` enum such as `active` / `disabled`
  - `must_reset_password`
  - `password_changed_at`
  - `session_version`
  - hashed recovery-code or reset-token fields plus expiry metadata needed by later tasks
- [ ] Add the Alembic migration for the new user fields.
- [ ] Add explicit bootstrap auth-mode selection support:
  - `auth_mode` request field in bootstrap initialize/configure requests
  - bootstrap state response includes supported auth modes and the selected mode
  - built-in IAM is the only accepted value in this phase
- [ ] Update bootstrap validation so completion fails if no explicit auth mode has been selected.
- [ ] Unit tests must cover:
  - built-in auth mode is persisted and echoed in bootstrap state
  - unsupported auth modes are rejected cleanly
  - bootstrap completion still works once built-in mode is selected and runtime checks pass

**Verification**

Run:

```powershell
$env:PYTHONPATH="services/control-plane;packages/platform_sdk;packages/platform_cli"
py -3.13 -m pytest tests/unit/test_bootstrap_service.py -q
```

Expected: PASS

## Task 2: Add Password Policy, Cookie Sessions, And Recovery Flows

**Files:**
- Create: `services/control-plane/app/services/auth_service.py`
- Modify: `services/control-plane/app/schemas/auth.py`
- Modify: `services/control-plane/app/api/auth.py`
- Modify: `services/control-plane/app/core/security.py`
- Modify: `services/control-plane/app/core/dependencies.py`
- Create: `tests/unit/test_auth_service.py`
- Create: `tests/integration/test_auth_sessions.py`

- [ ] Centralize password-policy validation in `auth_service` and apply it to:
  - bootstrap admin creation
  - admin-created users
  - password reset
  - recovery completion
- [ ] Introduce browser-session cookie support:
  - login sets an `HttpOnly` session cookie
  - logout clears it
  - auth dependencies accept either bearer token or session cookie
  - token payload includes `session_version` so admin actions and password resets can revoke old sessions
- [ ] Keep bearer-token response compatibility for non-browser clients while moving the frontend off token storage.
- [ ] Add a built-in recovery path for the bootstrap admin:
  - generate a one-time recovery code
  - store only the hash server-side
  - complete recovery by exchanging the code for a new password and incrementing `session_version`
- [ ] Add auth endpoints needed by the frontend and operator flow:
  - `POST /auth/logout`
  - recovery start/complete endpoints
  - any helper endpoint needed to expose current session user cleanly
- [ ] Tests must cover:
  - password policy accepts strong passwords and rejects weak ones
  - login sets the session cookie
  - `/auth/me` works with the cookie alone
  - logout clears the cookie
  - recovery completion rotates `session_version` and invalidates old sessions

**Verification**

Run:

```powershell
$env:PYTHONPATH="services/control-plane;packages/platform_sdk;packages/platform_cli"
py -3.13 -m pytest tests/unit/test_auth_service.py tests/integration/test_auth_sessions.py -q
```

Expected: PASS

## Task 3: Add Admin User Lifecycle Management APIs

**Files:**
- Create: `services/control-plane/app/services/user_management_service.py`
- Create: `services/control-plane/app/schemas/admin_users.py`
- Modify: `services/control-plane/app/api/admin.py`
- Create: `tests/integration/test_admin_user_management.py`

- [ ] Add admin APIs for workspace user lifecycle:
  - list users with status and reset requirements
  - create user with role and initial password
  - update role and status
  - generate reset or recovery actions without database edits
- [ ] Disabling a user must revoke existing sessions by incrementing `session_version`.
- [ ] Prevent the bootstrap admin from accidentally disabling the only active admin account.
- [ ] Return structured data that the frontend can render directly for the management page.
- [ ] Integration tests must cover:
  - admin creates a developer or user account
  - admin changes role or disables a user
  - disabled users cannot authenticate
  - admin can generate a reset or recovery action for another user

**Verification**

Run:

```powershell
$env:PYTHONPATH="services/control-plane;packages/platform_sdk;packages/platform_cli"
py -3.13 -m pytest tests/integration/test_admin_user_management.py -q
```

Expected: PASS

## Task 4: Replace Frontend Token Storage And Add User Management UI

**Files:**
- Modify: `frontend/app/setup/page.tsx`
- Modify: `frontend/app/login/page.tsx`
- Modify: `frontend/app/admin/layout.tsx`
- Create: `frontend/app/admin/users/page.tsx`
- Create: `frontend/components/UserManagementPanel.tsx`
- Modify: `frontend/components/AppShell.tsx`
- Modify: `frontend/components/BootstrapSetupWizard.tsx`
- Modify: `frontend/components/RoleGuard.tsx`
- Modify: `frontend/components/PlatformDocs.tsx`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/lib/auth.ts`
- Modify: `frontend/lib/types.ts`

- [ ] Replace frontend reliance on `localStorage` bearer tokens:
  - session cookie becomes the primary browser auth mechanism
  - auth helpers use `/auth/me` to resolve the current user
  - logout calls the backend endpoint before clearing client-side caches
- [ ] Update setup UI so built-in IAM is an explicit first-run choice and its copy explains that external IAM arrives in the next phase.
- [ ] Update the login flow to work without browser-managed bearer tokens and to surface recovery-entry points.
- [ ] Add an admin users page for:
  - listing users
  - creating users
  - changing role or status
  - generating reset or recovery actions
- [ ] Update in-app docs to explain built-in IAM behavior and the admin recovery path.

**Verification**

Run:

```bash
npm --prefix frontend run build
```

Expected: PASS, including `/setup`, `/login`, and `/admin/users`

## Task 5: Document And Certify The Built-In IAM Operator Flow

**Files:**
- Modify: `docs/self-hosting.md`
- Create: `tests/integration/test_built_in_iam_bootstrap.py`

- [ ] Document the built-in IAM first-run flow and the bootstrap-admin recovery path in self-hosting docs.
- [ ] Add an end-to-end app-level integration test for:
  - selecting built-in IAM during bootstrap
  - completing setup
  - authenticating via cookie session afterward
  - recovering the bootstrap admin via the documented recovery path
- [ ] Record any explicit deferrals for OIDC or advanced security features so readers do not confuse this phase with the later OIDC task.

**Verification**

Run:

```powershell
$env:PYTHONPATH="services/control-plane;packages/platform_sdk;packages/platform_cli"
py -3.13 -m pytest tests/integration/test_built_in_iam_bootstrap.py tests/integration/test_auth_sessions.py tests/integration/test_admin_user_management.py -q
npm --prefix frontend run build
```

Expected: PASS

## Final Verification

Run:

```powershell
$env:PYTHONPATH="services/control-plane;packages/platform_sdk;packages/platform_cli"
py -3.13 -m pytest ^
  tests/unit/test_bootstrap_service.py ^
  tests/unit/test_auth_service.py ^
  tests/unit/test_runtime_security_settings.py ^
  tests/integration/test_bootstrap_flow.py ^
  tests/integration/test_bootstrap_lockout.py ^
  tests/integration/test_built_in_iam_bootstrap.py ^
  tests/integration/test_auth_sessions.py ^
  tests/integration/test_admin_user_management.py -q
npm --prefix frontend run build
docker compose -f docker-compose.yml -f docker-compose.prod.yml config
```

Expected: PASS

Manual smoke once the stack is running:

- fresh instance lands in `/setup` and explicitly selects built-in IAM
- bootstrap admin completes setup and receives a browser cookie session
- admin creates a second user from `/admin/users`
- disabled users cannot sign in
- bootstrap admin recovery code flow restores access and invalidates older sessions

## Commit Boundary

- Commit 1: user model, bootstrap auth-mode persistence, and auth service foundations
- Commit 2: auth APIs, session cookies, and recovery flows
- Commit 3: admin user-management APIs and frontend/session UI updates
