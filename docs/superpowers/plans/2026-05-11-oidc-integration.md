# OIDC Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to execute this plan task by task. This plan is the dedicated child plan required by Task 3 of `2026-05-11-production-readiness-gap-closure.md`. It builds on the Built-In IAM Foundation child plan (`2026-05-11-built-in-iam-foundation.md`) and assumes its cookie sessions, `session_version` revocation, and admin user-management APIs are already in place.

**Goal:** Add external IAM via OpenID Connect to the self-hosted control plane so an admin can register an OIDC provider after setup, end users can sign in with SSO, the provider's claims drive role assignment with safe JIT provisioning, and the operator can either keep built-in IAM running side-by-side or make OIDC authoritative without locking themselves out.

**Architecture:** Treat OIDC as an additional authentication path that produces the same `User`/`session_version`/cookie session artifacts already issued by built-in IAM, so all downstream authorization keeps working unchanged. Persist provider config in a dedicated `oidc_provider` row (one active provider per instance in this phase) with the client secret encrypted via the existing `PLATFORM_SECRETS_KEY` Fernet store. Link external identities to local `User` rows through a new `user_identity` table so a single human can have both a built-in password and an OIDC identity (required for the bootstrap admin break-glass path). Use Authlib's `OAuth2Session`/`OAuth2Client` with the provider's discovery document for the authorization-code-with-PKCE flow, validate `state` and `nonce` from server-side cache backed by the database, and complete login by setting the same `platform_session` cookie that built-in login uses. Surface `auth_mode` values `built_in`, `hybrid`, and `oidc` so the operator can choose whether built-in login is allowed when OIDC is active.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Authlib (`authlib[client]`), `httpx` for discovery/JWKS fetches, Fernet via `app.services.secret_store`, Next.js 14 app router, pytest with app-level integration coverage backed by a responses/`respx`-style HTTP mock for the IdP

---

## Assumptions Locked For This Plan

- Exactly one OIDC provider is supported per instance in this phase; the schema allows multiple rows but the API and UI surface a single active provider. Multi-provider work is explicitly deferred to a later plan.
- Authorization-code flow with PKCE only. Implicit, hybrid response types, and client-secret-in-URL flows are not implemented.
- The control plane talks to the IdP server-side. The browser only sees redirects to the provider, the callback URL on the control plane, and the resulting cookie session — no client-side OIDC libraries.
- Provider configuration is admin-only and lands after bootstrap. The bootstrap wizard does not configure OIDC in this phase, but bootstrap state's `supported_auth_modes` now advertises `built_in`, `hybrid`, and `oidc`, and the setup wizard explains that OIDC is configurable after first login.
- The bootstrap admin always retains a built-in password and recovery code so OIDC misconfiguration cannot lock the operator out. When `auth_mode == "oidc"`, built-in login is disabled for everyone else; the bootstrap admin can still sign in with built-in credentials and is the only break-glass account.
- Role mapping is config-driven via `role_claim` (claim name) and an explicit `claim_role_map` JSON object. If the incoming claim does not map, the user receives the configured `default_role` and the event is logged for the admin to act on.
- JIT provisioning creates a `User` and a `user_identity` row tied to the instance's only tenant. Existing users are linked on first SSO login when the OIDC `email` claim matches an active local account (case-insensitive). Email-mismatched logins are rejected to prevent account takeover.
- All OIDC state, including `state` and `nonce`, is stored server-side in a short-lived `oidc_auth_request` table indexed by an opaque cookie. No state is trusted from query string alone.
- This phase touches `docs/self-hosting.md` and the in-app docs to describe configuring OIDC and the break-glass behavior, but the broader self-hosting documentation pass remains the final certification task.

## File Structure

**Create:**
- `services/control-plane/app/models/oidc_provider.py`
- `services/control-plane/app/models/user_identity.py`
- `services/control-plane/app/models/oidc_auth_request.py`
- `services/control-plane/app/schemas/oidc.py`
- `services/control-plane/app/services/oidc_provider_service.py`
- `services/control-plane/app/services/oidc_login_service.py`
- `services/control-plane/app/api/oidc.py`
- `services/control-plane/alembic/versions/0007_oidc_integration.py`
- `tests/unit/test_oidc_provider_service.py`
- `tests/unit/test_oidc_login_service.py`
- `tests/integration/test_oidc_admin_config.py`
- `tests/integration/test_oidc_login_flow.py`
- `tests/integration/test_oidc_authoritative_mode.py`
- `frontend/app/admin/auth/page.tsx`
- `frontend/components/OidcProviderForm.tsx`
- `frontend/components/SsoLoginButton.tsx`

**Modify:**
- `services/control-plane/app/models/__init__.py`
- `services/control-plane/app/main.py`
- `services/control-plane/app/api/auth.py`
- `services/control-plane/app/api/bootstrap.py`
- `services/control-plane/app/core/dependencies.py`
- `services/control-plane/app/services/auth_service.py`
- `services/control-plane/app/services/bootstrap_service.py`
- `services/control-plane/app/services/secret_store.py` (only if a helper is missing — otherwise reuse as-is)
- `services/control-plane/app/schemas/bootstrap.py`
- `services/control-plane/app/schemas/auth.py`
- `services/control-plane/pyproject.toml` (add `authlib`, `respx` test dep)
- `frontend/app/login/page.tsx`
- `frontend/app/admin/layout.tsx`
- `frontend/components/BootstrapSetupWizard.tsx`
- `frontend/components/PlatformDocs.tsx`
- `frontend/lib/api.ts`
- `frontend/lib/auth.ts`
- `frontend/lib/types.ts`
- `docs/self-hosting.md`

## Task 1: Data Model, Migration, And Auth-Mode Extension

**Files:**
- Create: `services/control-plane/app/models/oidc_provider.py`
- Create: `services/control-plane/app/models/user_identity.py`
- Create: `services/control-plane/app/models/oidc_auth_request.py`
- Modify: `services/control-plane/app/models/__init__.py`
- Modify: `services/control-plane/app/models/user.py`
- Create: `services/control-plane/alembic/versions/0007_oidc_integration.py`
- Modify: `services/control-plane/app/services/bootstrap_service.py`
- Modify: `services/control-plane/app/schemas/bootstrap.py`
- Modify: `tests/unit/test_bootstrap_service.py`

- [ ] Add `OidcProvider` model with fields:
  - `id` (UUID), `name` (display label), `issuer`, `client_id`, `client_secret_encrypted` (Fernet-encrypted via the existing secret store), `discovery_url`, `scopes` (default `"openid email profile"`), `email_claim` (default `"email"`), `role_claim` (nullable), `claim_role_map` (JSON), `default_role` (UserRole, default `user`), `allow_jit_provisioning` (bool, default true), `is_enabled` (bool), `created_at`, `updated_at`.
- [ ] Add `UserIdentity` model linking a `User` to an `(provider, subject)` pair with unique constraint on `(provider_id, subject)` and an index on `user_id`. Track `email_at_login`, `last_login_at`.
- [ ] Add `OidcAuthRequest` model with `id` (UUID, used as the opaque flow cookie), `provider_id`, `state`, `nonce`, `pkce_verifier`, `redirect_after_login`, `expires_at`. Records expire 10 minutes after creation and are deleted on consume.
- [ ] Make `User.password_hash` nullable so OIDC-only users can exist without a built-in password. Existing rows keep their hash; new OIDC users get `NULL` and cannot use built-in login. Bootstrap admin retains a password.
- [ ] Extend `bootstrap_service.SUPPORTED_AUTH_MODES` to include `"hybrid"` and `"oidc"`. Keep the bootstrap initialize default at `"built_in"`; allow operators to move to `"hybrid"` or `"oidc"` later via `/bootstrap/configure` *only after* a provider is configured. Add a helper `validate_auth_mode_for_state` that rejects `"hybrid"`/`"oidc"` when there is no enabled provider.
- [ ] Update `BootstrapStatePublic` and `BootstrapConfigureRequest` schemas to reflect the expanded `supported_auth_modes` and to surface a derived `auth_mode_enforced` field (`"oidc"`, `"hybrid"`, or `"built_in"`).
- [ ] Add Alembic migration `0007_oidc_integration.py` that:
  - alters `user.password_hash` to nullable
  - creates `oidc_provider`, `user_identity`, `oidc_auth_request`
  - adds the appropriate indexes and unique constraints
- [ ] Unit tests must cover:
  - `User.password_hash` accepts null
  - `bootstrap_service.validate_auth_mode_for_state` rejects `"oidc"`/`"hybrid"` until a provider exists
  - bootstrap state surfaces the expanded supported modes

**Verification**

Run:

```powershell
$env:PYTHONPATH="services/control-plane;packages/platform_sdk;packages/platform_cli"
py -3.13 -m pytest tests/unit/test_bootstrap_service.py -q
```

Expected: PASS

## Task 2: OIDC Provider Configuration Service And Admin API

**Files:**
- Create: `services/control-plane/app/services/oidc_provider_service.py`
- Create: `services/control-plane/app/schemas/oidc.py`
- Create: `services/control-plane/app/api/oidc.py`
- Modify: `services/control-plane/app/main.py` (register router)
- Modify: `services/control-plane/pyproject.toml` (add `authlib`)
- Create: `tests/unit/test_oidc_provider_service.py`
- Create: `tests/integration/test_oidc_admin_config.py`

- [ ] Implement `oidc_provider_service` with:
  - `create_or_update_provider(...)` — validates discovery URL and issuer reachability by fetching the discovery doc with a short timeout, persists provider with `client_secret` encrypted via the existing Fernet helper, returns a redacted view.
  - `get_active_provider(db)` and `get_provider_public_view(provider)` — never expose `client_secret_encrypted`; only echo a `has_client_secret` boolean.
  - `enable_provider` / `disable_provider` — disabling demotes `auth_mode` to `built_in` if it was `oidc` or `hybrid`, with an audit log entry so the operator sees what happened.
  - `delete_provider` — only allowed when no users have OIDC-only identities, or when the caller passes an `allow_orphaning` flag and at least one admin retains a built-in password.
- [ ] Implement `POST/PUT/GET/DELETE /admin/oidc/provider` routes guarded by `require_role("admin")`:
  - `GET` returns the redacted provider and the resolved discovery metadata (issuer, supported scopes, JWKS URI).
  - `PUT` upserts. Accept `client_secret` in plaintext only; reject empty string updates (require an explicit `rotate=true` flag with new secret).
  - `DELETE` removes provider; if `auth_mode` was `oidc`/`hybrid`, demote to `built_in`.
- [ ] Add `POST /admin/oidc/test-discovery` for an admin to validate a candidate `discovery_url` without saving — useful for setup forms.
- [ ] Add `oidc.py` schemas: `OidcProviderPublic`, `OidcProviderUpsertRequest`, `OidcDiscoveryProbeRequest`, `OidcDiscoveryProbeResponse`, `OidcClaimRoleMap`.
- [ ] Integration tests must cover:
  - admin can create, fetch, update, and delete a provider
  - non-admin requests return 403
  - `client_secret` never appears in any response payload
  - invalid discovery URL returns a 422 with an actionable error
  - deleting the provider while `auth_mode == "oidc"` demotes mode to `built_in`

**Verification**

Run:

```powershell
$env:PYTHONPATH="services/control-plane;packages/platform_sdk;packages/platform_cli"
py -3.13 -m pytest tests/unit/test_oidc_provider_service.py tests/integration/test_oidc_admin_config.py -q
```

Expected: PASS

## Task 3: OIDC Authorization-Code Flow With PKCE And Cookie Session Issuance

**Files:**
- Create: `services/control-plane/app/services/oidc_login_service.py`
- Modify: `services/control-plane/app/api/oidc.py`
- Modify: `services/control-plane/app/api/auth.py`
- Modify: `services/control-plane/app/services/auth_service.py` (add `establish_session(user, response)` helper if it makes the call sites cleaner — otherwise reuse existing helpers directly)
- Create: `tests/unit/test_oidc_login_service.py`
- Create: `tests/integration/test_oidc_login_flow.py`

- [ ] Implement `oidc_login_service.start_login(db, provider, redirect_after_login)`:
  - generates `state`, `nonce`, PKCE verifier/challenge
  - inserts an `OidcAuthRequest` row with 10-minute TTL
  - returns the IdP authorization URL plus an opaque `flow_id` (the request row's UUID) for the cookie
- [ ] Implement `oidc_login_service.complete_login(db, provider, *, flow_id, returned_state, code, response)`:
  - looks up and consumes the `OidcAuthRequest` row in a single transaction; rejects expired or already-consumed rows
  - validates `returned_state == row.state`
  - exchanges `code` for tokens via Authlib using the stored PKCE verifier
  - verifies `id_token` against the provider's JWKS; validates `iss`, `aud`, `exp`, and `nonce`
  - resolves the local `User`: existing match by `(provider, subject)` via `user_identity`, then fallback to active local user with matching email (link), else JIT-provision if `allow_jit_provisioning` is true. Email-mismatched or disabled accounts are rejected with a structured error.
  - on success: sets the same `platform_session` cookie used by built-in login (reuse `auth_service.create_session_token` + `set_session_cookie`), increments nothing on the user (existing session_version is fine for the new login), updates `user_identity.last_login_at`
- [ ] Implement endpoints:
  - `GET /auth/oidc/start?next=...` — looks up the active provider, calls `start_login`, sets a short-lived `oidc_flow` cookie (`HttpOnly`, `SameSite=Lax`, ~10 minutes) with the `flow_id`, then 303-redirects to the IdP authorization URL.
  - `GET /auth/oidc/callback?code=...&state=...&error=...` — validates `oidc_flow` cookie presence, looks up the matching `OidcAuthRequest`, calls `complete_login`, clears the `oidc_flow` cookie, and redirects to the `redirect_after_login` URL (or `/` if unset). All error paths render a structured JSON response when `Accept: application/json`, otherwise redirect to `/login?oidc_error=...` with a stable error code (`invalid_state`, `expired_flow`, `email_mismatch`, `provisioning_disabled`, `idp_error`, `unknown`).
- [ ] `GET /auth/oidc/status` — returns whether OIDC is enabled, the provider's display name, the `auth/oidc/start` URL, and whether built-in login is allowed (driven by `auth_mode`).
- [ ] Unit tests must cover:
  - `start_login` persists a row with non-empty `state`, `nonce`, and PKCE verifier
  - `complete_login` rejects state mismatch, expired rows, replayed rows, missing/invalid `id_token`, disabled users, and email mismatch
  - JIT provisioning creates a `User` and a linked `user_identity`
  - existing email match links the identity without rotating the user's `session_version`
- [ ] Integration tests must cover (using mocked IdP via `respx`):
  - happy path produces a cookie session and redirects to `next`
  - replay attack on a consumed flow returns `invalid_state` and does not authenticate
  - `id_token` with wrong `aud` is rejected
  - JIT-provisioned user can call `/auth/me` immediately after callback
  - disabling the OIDC-provisioned user revokes their cookie session

**Verification**

Run:

```powershell
$env:PYTHONPATH="services/control-plane;packages/platform_sdk;packages/platform_cli"
py -3.13 -m pytest tests/unit/test_oidc_login_service.py tests/integration/test_oidc_login_flow.py -q
```

Expected: PASS

## Task 4: Claim-To-Role Mapping, Built-In Disablement, And Bootstrap Break-Glass

**Files:**
- Modify: `services/control-plane/app/services/oidc_login_service.py`
- Modify: `services/control-plane/app/api/auth.py`
- Modify: `services/control-plane/app/services/auth_service.py`
- Modify: `services/control-plane/app/services/bootstrap_service.py`
- Modify: `services/control-plane/app/services/oidc_provider_service.py`
- Create: `tests/integration/test_oidc_authoritative_mode.py`

- [ ] Implement claim-to-role resolution in `oidc_login_service.resolve_role(provider, claims)`:
  - if `role_claim` is configured, look up the claim value (string or list of strings) and find the first match in `claim_role_map`
  - fall back to `default_role`
  - returns the resolved role plus a structured `resolution_trace` for logging/admin debugging
- [ ] Apply resolved role on JIT provisioning. For an existing linked user, leave their role unchanged unless the provider has `manage_roles=true` (default false). The role-management flag is exposed in the provider schema.
- [ ] Add built-in login enforcement gate. In `auth.py` login route:
  - read `auth_mode` and the active provider state via `bootstrap_service.get_bootstrap_state`
  - when `auth_mode == "oidc"`, reject built-in login with `423 LOCKED` **unless** the user being authenticated matches the bootstrap admin email (break-glass). Break-glass logins are audit-logged.
  - when `auth_mode == "hybrid"`, allow both paths
- [ ] Add `auth_service.is_built_in_login_allowed(state, *, email)` helper covering the break-glass logic so both the API gate and tests share the rule.
- [ ] Update `/bootstrap/configure` so transitioning to `"oidc"` only succeeds when:
  - at least one provider exists and is enabled
  - the bootstrap admin still has a built-in password (preventing self-lockout)
- [ ] Update `BootstrapStatePublic` with two derived fields the frontend can read:
  - `built_in_login_enabled` (bool)
  - `bootstrap_admin_email` (already present, used for the break-glass hint)
- [ ] Integration tests must cover:
  - role-claim mapping for new and existing users
  - `manage_roles=false` does not change an existing user's role
  - `manage_roles=true` updates role on subsequent login
  - `auth_mode == "oidc"` blocks built-in login for non-bootstrap users
  - bootstrap admin can still complete `/auth/login` when `auth_mode == "oidc"` (break-glass)
  - `auth_mode == "hybrid"` allows both paths

**Verification**

Run:

```powershell
$env:PYTHONPATH="services/control-plane;packages/platform_sdk;packages/platform_cli"
py -3.13 -m pytest tests/integration/test_oidc_authoritative_mode.py -q
```

Expected: PASS

## Task 5: Frontend — Admin Auth Settings, SSO Login Button, And Setup Copy

**Files:**
- Create: `frontend/app/admin/auth/page.tsx`
- Create: `frontend/components/OidcProviderForm.tsx`
- Create: `frontend/components/SsoLoginButton.tsx`
- Modify: `frontend/app/admin/layout.tsx`
- Modify: `frontend/app/login/page.tsx`
- Modify: `frontend/components/BootstrapSetupWizard.tsx`
- Modify: `frontend/components/PlatformDocs.tsx`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/lib/auth.ts`
- Modify: `frontend/lib/types.ts`

- [ ] Add `OidcProviderConfig` and `OidcStatus` types in `frontend/lib/types.ts` mirroring the backend schemas.
- [ ] Add an admin page at `/admin/auth` that:
  - displays the current provider (redacted) and whether it is enabled
  - lets the admin probe a discovery URL before saving
  - lets the admin upsert client_id, client_secret, scopes, claim mapping, and role mapping
  - lets the admin toggle `auth_mode` between `built_in`, `hybrid`, and `oidc`, with a confirmation dialog that names the bootstrap admin as the break-glass account when switching to `oidc`
- [ ] Add an SSO login button on `/login` that:
  - fetches `/api/auth/oidc/status` on mount
  - renders `Continue with <provider name>` and links to `/api/auth/oidc/start?next=<intended path>`
  - hides itself if OIDC is disabled
  - shows a banner explaining built-in login is the break-glass account when `auth_mode == "oidc"` and the visitor is not the bootstrap admin email
- [ ] Surface OIDC error codes from the callback redirect (`/login?oidc_error=...`) as user-friendly copy.
- [ ] Update `BootstrapSetupWizard.tsx` to advertise the available auth modes and explain that OIDC is configured after first login under Admin → Authentication.
- [ ] Update in-app docs in `PlatformDocs.tsx` to describe configuring OIDC, role mapping, and the bootstrap-admin break-glass flow.
- [ ] Ensure `frontend/lib/auth.ts` still treats the cookie session as primary — no new local-storage tokens.

**Verification**

Run:

```bash
npm --prefix frontend run build
```

Expected: PASS, including `/admin/auth`, `/login` with SSO button when OIDC is enabled, and the updated `/setup` copy.

## Task 6: Documentation And End-To-End Operator Certification

**Files:**
- Modify: `docs/self-hosting.md`
- Modify: `frontend/components/PlatformDocs.tsx`

- [ ] Document the OIDC configuration flow in self-hosting docs:
  - register an app at the IdP with redirect URI `<base>/api/auth/oidc/callback`
  - copy `client_id` and `client_secret` into Admin → Authentication
  - choose scopes and claim mapping
  - probe the discovery URL
  - flip `auth_mode` to `hybrid` first, verify SSO sign-in, then optionally flip to `oidc`
- [ ] Document the break-glass behavior, including how the bootstrap admin signs in when OIDC is broken and how to use the existing recovery code if their password is lost.
- [ ] Record explicit deferrals: multiple providers, per-tenant providers, SAML, OIDC RP-initiated logout, and provider-driven user provisioning (SCIM).
- [ ] Sanity-check operator path on a fresh deployment (manual, not test-suite gated):
  - fresh setup completes with `auth_mode == "built_in"`
  - admin registers an OIDC provider and probes discovery successfully
  - admin switches `auth_mode` to `hybrid`, signs out, signs back in via SSO
  - JIT-provisioned user lands with the expected role
  - admin disables OIDC, built-in login still works

**Verification**

Run:

```powershell
$env:PYTHONPATH="services/control-plane;packages/platform_sdk;packages/platform_cli"
py -3.13 -m pytest ^
  tests/unit/test_bootstrap_service.py ^
  tests/unit/test_oidc_provider_service.py ^
  tests/unit/test_oidc_login_service.py ^
  tests/integration/test_oidc_admin_config.py ^
  tests/integration/test_oidc_login_flow.py ^
  tests/integration/test_oidc_authoritative_mode.py ^
  tests/integration/test_auth_sessions.py ^
  tests/integration/test_built_in_iam_bootstrap.py ^
  tests/integration/test_admin_user_management.py -q
npm --prefix frontend run build
docker compose -f docker-compose.yml -f docker-compose.prod.yml config
```

Expected: PASS

## Final Verification Checklist

- [ ] A fresh deployment can configure at least one OIDC provider from the admin UI without database edits.
- [ ] Role mapping resolves new users and existing users according to documented rules.
- [ ] Built-in IAM still works end-to-end when no OIDC provider is configured (`auth_mode == "built_in"`).
- [ ] When `auth_mode == "oidc"`, all non-bootstrap users go through SSO; the bootstrap admin can still recover via built-in login or recovery code.
- [ ] `id_token` validation (`iss`, `aud`, `exp`, `nonce`), `state` validation, PKCE, and replay prevention all have explicit tests.
- [ ] No client secret, ID token, or access token ever lands in a response body or log line.

## Commit Boundary

- Commit 1: data model + migration + auth-mode extension
- Commit 2: provider configuration service, schemas, and admin API
- Commit 3: OIDC authorization-code flow, callback, and session issuance
- Commit 4: claim-to-role mapping, built-in disablement, and break-glass
- Commit 5: frontend admin settings, SSO login button, and setup/docs copy
