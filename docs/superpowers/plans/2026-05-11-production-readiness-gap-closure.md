# Production Readiness Gap Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining gaps between the original production-readiness prompt and the current Phase 1/2 implementation so the platform can move from a hardened prototype to a self-hostable production baseline.

**Architecture:** Treat the current `codex/production-phase-1` branch as the baseline: Phase 1 hardening is in place and Phase 2 bootstrap exists, but the platform still lacks full IAM, Git-backed skill distribution, and the broader security/release program. Resolve the remaining bootstrap quality gaps first, then ship built-in IAM, then OIDC, then Git-backed skills, then security/operations gates, and finish with a fresh-deployment certification pass.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Next.js 14, Docker Compose, pytest, Playwright or equivalent browser automation, OIDC library (for example Authlib), Git archive validation, CI security tooling

---

## Current Assessment Snapshot

**Implemented well enough to build on**

- same-origin frontend proxying and production-baseline docs
- production secret validation in service startup settings
- schedule timezone handling with focused unit coverage
- in-app documentation tab for admin/developer/user roles
- first-run bootstrap state, bootstrap gating, and `/setup` route

**Still missing against the original prompt**

- configure mode does not let the operator choose or configure an IAM mode yet
- built-in IAM is still just the old email/password model plus roles, not a production auth subsystem
- external IAM/OIDC is not implemented
- Git-backed skill registry and downloadable skill tree/prompt flow are not implemented
- CI/release/security/observability program is not implemented
- bootstrap flow lacks automated end-to-end coverage for first-run, partial setup, completion, and lockout prevention

## File Structure

**Create:**
- `docs/superpowers/plans/2026-05-11-built-in-iam-foundation.md`
- `docs/superpowers/plans/2026-05-11-oidc-integration.md`
- `docs/superpowers/plans/2026-05-11-git-backed-skill-registry.md`
- `docs/superpowers/plans/2026-05-11-security-observability-release-gates.md`
- `tests/integration/test_bootstrap_flow.py`
- `tests/integration/test_bootstrap_lockout.py`

**Modify:**
- `docs/superpowers/plans/2026-05-11-bootstrap-configure-mode.md`
- `services/control-plane/app/services/bootstrap_service.py`
- `services/control-plane/app/api/bootstrap.py`
- `frontend/components/BootstrapSetupWizard.tsx`
- `README.md`

## Task 1: Close The Bootstrap Quality Gaps Before Starting IAM

**Files:**
- Modify: `docs/superpowers/plans/2026-05-11-bootstrap-configure-mode.md`
- Create: `tests/integration/test_bootstrap_flow.py`
- Create: `tests/integration/test_bootstrap_lockout.py`
- Modify: `services/control-plane/app/services/bootstrap_service.py`
- Modify: `services/control-plane/app/api/bootstrap.py`
- Modify: `frontend/components/BootstrapSetupWizard.tsx`

- [ ] Add a short dated note to the bootstrap child plan recording the current deviation from the Phase 2 checklist:
  - only unit tests exist today
  - no IAM mode selection exists yet
  - no automated first-run browser/API flow exists yet
- [ ] Write failing integration coverage for:
  - fresh instance returns bootstrap-required state
  - anonymous second bootstrap initialization is rejected
  - bootstrap admin can log back in and resume partial setup
  - normal API routes return bootstrap lock errors before completion
- [ ] Run the new tests to confirm they fail for the right missing behavior.
- [ ] Implement the minimum backend/frontend fixes required for those tests to pass.
- [ ] Extend the setup UI to show operator guidance for blocked runtime checks, not just status badges.
- [ ] Re-run:

```powershell
$env:PYTHONPATH="services/control-plane;packages/platform_sdk;packages/platform_cli"
py -3.13 -m pytest tests/unit/test_bootstrap_service.py tests/unit/test_runtime_security_settings.py tests/integration/test_bootstrap_flow.py tests/integration/test_bootstrap_lockout.py -q
npm --prefix frontend run build
```

Expected: PASS

## Task 2: Write And Execute The Built-In IAM Foundation Plan

**Files:**
- Create: `docs/superpowers/plans/2026-05-11-built-in-iam-foundation.md`
- Modify later during execution: `services/control-plane/app/models/user.py`, `services/control-plane/app/api/auth.py`, `services/control-plane/app/core/security.py`, `frontend/app/setup/page.tsx`, `frontend/components/BootstrapSetupWizard.tsx`, role/admin user-management pages, related tests

- [ ] Write the dedicated built-in IAM child plan before touching IAM product code.
- [ ] The child plan must cover:
  - instance-level auth mode selection persisted during bootstrap
  - built-in IAM as an explicit configure-mode option
  - local admin/workspace user lifecycle and admin UI for membership management
  - password policy, reset/recovery, and session-expiry behavior
  - hardening or replacing the current local-storage token model
  - backend, frontend, and browser/integration tests
- [ ] Execute the built-in IAM plan only after it includes explicit files, tests, and verification commands.
- [ ] Verify:
  - a fresh deployment can choose built-in IAM during setup
  - admin can create/manage users without raw DB edits
  - password-only mode works end to end
  - admin recovery path is documented and tested

## Task 3: Write And Execute The OIDC Integration Plan

**Files:**
- Create: `docs/superpowers/plans/2026-05-11-oidc-integration.md`
- Modify later during execution: new auth-provider models/services/routes, frontend auth settings UI, callback routes, tests

- [ ] Write the dedicated OIDC child plan before touching external IAM code.
- [ ] The child plan must cover:
  - provider configuration storage
  - callback handling, nonce/state validation, and secure error paths
  - claim/group-to-role mapping
  - JIT provisioning for new users
  - built-in-login disablement when OIDC is authoritative
  - login/logout/session-expiry behavior and tests
- [ ] Execute the OIDC plan.
- [ ] Verify:
  - at least one OIDC provider can be configured from a self-hosted deployment
  - role mapping works for new and existing users
  - built-in IAM still works when OIDC is disabled

## Task 4: Write And Execute The Git-Backed Skill Registry Plan

**Files:**
- Create: `docs/superpowers/plans/2026-05-11-git-backed-skill-registry.md`
- Modify later during execution: new skill-source models/services/jobs/UI/tests

- [ ] Write the dedicated Git-backed skill child plan before touching skill-registry code.
- [ ] The child plan must cover:
  - skill source schema with repo URL + ref/version + manifest metadata
  - clone/pull/update workflow and archive validation
  - safe extraction, traversal protection, and size limits
  - browsable extracted file tree in the UI
  - AI-facing prompt/instruction display or generation for non-technical local AI usage
  - malicious archive/update tests
- [ ] Execute the skill-registry plan.
- [ ] Verify:
  - admin can register a Git source and refresh it safely
  - user can inspect the full downloaded file tree
  - user can copy/view a usable non-technical prompt for local AI implementation/use

## Task 5: Write And Execute The Security, Observability, And Release-Gates Plan

**Files:**
- Create: `docs/superpowers/plans/2026-05-11-security-observability-release-gates.md`
- Modify later during execution: CI workflows, docs/runbooks, logging/metrics/audit code, security tests

- [ ] Write the dedicated security/ops child plan before touching release-gate code.
- [ ] The child plan must cover:
  - CI gates for unit/integration tests, lint/type checks, dependency scanning, image scanning, and secret detection
  - structured logs, metrics, and alert hooks
  - audit visibility for admin-sensitive actions
  - threat-model docs for control plane, tool gateway, runtime, and skill ingestion
  - access-control/auth/session/SSRF/archive/deserialization/CSRF/rate-limit validation
  - backup/restore/upgrade runbooks and drills
- [ ] Execute the security/ops plan.
- [ ] Verify:
  - failing tests or critical scans block release
  - operators have backup/restore/upgrade documentation they can follow without code edits
  - enough logs/metrics/audit data exist to support production troubleshooting

## Task 6: Run A Fresh-Deployment Certification Pass And Update Customer-Facing Docs

**Files:**
- Modify: `README.md`
- Modify: `docs/self-hosting.md`
- Modify as needed: in-app docs under `frontend/components/PlatformDocs.tsx`

- [ ] Start from a fresh checkout and empty database in a clean worktree.
- [ ] Verify the operator path from the original prompt:
  - launch with Docker
  - hit configure mode on first launch
  - choose built-in IAM or OIDC-capable setup path
  - complete setup
  - log in normally
  - register and inspect a Git-backed skill
  - run a manual job and a scheduled job
- [ ] Update README and self-hosting docs to match the actual shipped behavior, not the plan.
- [ ] Record any remaining gaps with explicit defer rationale and dated follow-up plans.

## Done Definition

- [ ] Bootstrap flow has automated end-to-end coverage, not just unit tests.
- [ ] Built-in IAM is a real supported auth mode, not just the legacy local login.
- [ ] OIDC works without regressing the built-in path.
- [ ] Git-backed skill distribution is shipped and safely validated.
- [ ] CI/security/observability/release gates are active and documented.
- [ ] A fresh self-hosted deployment can follow the documented operator flow from first launch to successful use.
