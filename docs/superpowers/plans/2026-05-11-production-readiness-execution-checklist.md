# Production Readiness Execution Checklist

> **For agentic workers:** Use `superpowers:executing-plans` on this file after the current dirty work has been preserved safely. Use the global worktree root `C:\Users\const\.config\superpowers\worktrees\Runnairs\` for implementation branches. When a phase below says to write a child plan, do that before touching product code for that phase.

**Goal:** Convert the strategic production roadmap into a safe, executable sequence that gets the platform from today's local prototype plus first hardening pass to a self-hostable production baseline with bootstrap gating, IAM, Git-backed skill distribution, and release/security controls.

**Why this file exists:** [2026-05-11-production-readiness-master-plan.md](C:\Users\const\OneDrive\Dokumente\NTU\Runnairs\docs\superpowers\plans\2026-05-11-production-readiness-master-plan.md) is the strategy document. This file is the execution driver.

## Current Repo Snapshot (2026-05-11)

- The repository is currently dirty on `main`; do not continue implementation on `main`.
- There is already an in-flight hardening pass touching:
  - same-origin frontend proxying via `frontend/app/api/[...path]/route.ts` and `frontend/lib/api.ts`
  - production secret validation in `services/control-plane/app/core/config.py` and `services/tool-gateway/app/config.py`
  - schedule timezone handling in `services/control-plane/app/services/schedule_service.py`
  - in-app documentation routes in `frontend/app/admin/docs/page.tsx`, `frontend/app/dev/docs/page.tsx`, `frontend/app/app/docs/page.tsx`, and `frontend/components/PlatformDocs.tsx`
  - operator documentation in `README.md`, `docs/self-hosting.md`, `.env.example`, and `docker-compose.prod.yml`
- Two detailed implementation plans already exist and should be reused instead of rewritten:
  - [2026-05-10-automation-platform-foundation.md](C:\Users\const\OneDrive\Dokumente\NTU\Runnairs\docs\superpowers\plans\2026-05-10-automation-platform-foundation.md)
  - [2026-05-10-deploy-safety-and-readiness-fixes.md](C:\Users\const\OneDrive\Dokumente\NTU\Runnairs\docs\superpowers\plans\2026-05-10-deploy-safety-and-readiness-fixes.md)

## Global Execution Rules

- [ ] Never implement directly on `main`; every coding phase must run in a worktree branch under `codex/`.
- [ ] Do not lose or overwrite the current dirty worktree state. Preserve it first with a commit on a temporary branch, an exported patch, or explicit user-approved stash/move workflow.
- [ ] Before each coding phase, verify whether a detailed child plan already exists. If it does, execute that plan. If it does not, write it first.
- [ ] Each phase must end with explicit verification commands and a short status note describing what shipped, what remains, and any blockers.
- [ ] Stop immediately if a baseline check fails in a clean worktree or if current dirty changes cannot be carried forward safely.

## Phase 0: Preflight, Branch Hygiene, and Baseline

- [ ] Review `git status --short --branch` and classify every dirty file as:
  - intended production-readiness work
  - unrelated user work that must stay untouched
  - obsolete experiment that should only be removed with explicit user approval
- [ ] Preserve intended production-readiness changes before worktree creation.
  - Recommended: create a temporary local branch from the current checkout, commit the intended changes there, then create the worktree from that branch.
  - Alternative: export a patch and re-apply it inside the worktree.
- [ ] Create a global worktree branch under `C:\Users\const\.config\superpowers\worktrees\Runnairs\`.
  - Suggested first branch: `codex/production-phase-1`
- [ ] In the clean worktree, run baseline verification before adding new behavior:
  - `npm --prefix frontend run build`
  - PowerShell: `$env:PYTHONPATH="services/control-plane;packages/platform_sdk;packages/platform_cli"; pytest tests/unit/test_schedule_service.py -q`
  - `docker compose -f docker-compose.yml -f docker-compose.prod.yml config`
- [ ] If baseline verification fails, stop and repair the baseline before opening a new implementation phase.

## Phase 1: Finish the Immediate Hardening Baseline

**Objective:** Close Workstream A and the production-doc subset of Workstream D using the existing concrete plans plus the current in-flight branch changes.

- [ ] Reconcile the current working-tree changes against the expected Phase 1 outcomes:
  - browser clients use the same-origin proxy instead of Docker-internal hostnames
  - production mode rejects weak/default JWT secrets
  - schedules compute `next_run_at` in the schedule timezone
  - in-app docs are available for admin, developer, and user views
  - self-hosting docs and production compose overlay are updated
- [ ] Execute the remaining applicable steps from [2026-05-10-deploy-safety-and-readiness-fixes.md](C:\Users\const\OneDrive\Dokumente\NTU\Runnairs\docs\superpowers\plans\2026-05-10-deploy-safety-and-readiness-fixes.md).
  - If equivalent code already exists in the worktree, validate it instead of re-implementing it.
  - If the existing work differs from the older plan, update the older plan or leave a short note explaining the deviation before continuing.
- [ ] Verify the production-baseline doc pass using:
  - `npm --prefix frontend run build`
  - PowerShell: `$env:PYTHONPATH="services/control-plane;packages/platform_sdk;packages/platform_cli"; pytest tests/unit/test_schedule_service.py -q`
  - `docker compose -f docker-compose.yml -f docker-compose.prod.yml config`
- [ ] Add any missing focused tests from the deploy-safety plan before calling Phase 1 complete.
- [ ] Capture the result in one or more logical commits.

**Phase 1 exit criteria**

- [ ] Frontend API calls work through the Next.js proxy layer.
- [ ] Production startup rejects weak secrets in both the control plane and tool gateway.
- [ ] Schedule timezone behavior is covered by automated tests.
- [ ] README and self-hosting docs describe the supported production baseline and its limits.
- [ ] The in-app documentation tab is visible in all three role areas.

## Phase 2: Bootstrap State and First-Run Configure Mode

**Objective:** Implement Workstream B so a fresh deployment cannot be used normally until it has been configured safely.

- [ ] Write a dedicated child plan at `docs/superpowers/plans/2026-05-11-bootstrap-configure-mode.md`.
- [ ] The child plan must cover:
  - schema for `instance_settings` and/or `instance_bootstrap_state`
  - backend APIs to read bootstrap state and submit setup progress
  - instance admin creation and secure secret validation
  - storage/database health checks and required mail/notification defaults
  - gating logic that redirects normal app/login routes into setup mode until bootstrap completes
  - automated backend and frontend tests for first-run, partial setup, completed setup, and lockout prevention
- [ ] Execute that child plan only after it contains explicit files, tests, and verification commands.
- [ ] Verify:
  - fresh instance returns bootstrap-required state before normal login
  - setup completion flips the instance into normal mode without manual DB edits
  - reloading the frontend after partial setup resumes the wizard safely

**Phase 2 exit criteria**

- [ ] First launch always enters configure mode.
- [ ] Normal app routes remain blocked until bootstrap completes.
- [ ] A safe instance admin and core security secrets are required before unlock.

## Phase 3: Built-In IAM Foundation

**Objective:** Deliver the built-in IAM path required by the master plan before external IAM is added.

- [ ] Write a dedicated child plan at `docs/superpowers/plans/2026-05-11-built-in-iam-foundation.md`.
- [ ] The child plan must cover:
  - instance-level auth configuration state
  - local admin and workspace user lifecycle
  - password policy and secure reset flows
  - session expiry behavior and login/logout handling
  - role assignment and admin UI for workspace membership management
  - tests for login, denial, role changes, and password-only mode
- [ ] Execute the child plan.
- [ ] Verify:
  - the built-in IAM path works end to end on a fresh self-hosted deployment
  - local admin recovery flows are documented and tested
  - the current local-storage token model is either hardened for this phase or an explicit session migration plan is captured before moving on

**Phase 3 exit criteria**

- [ ] Built-in IAM is the supported default production auth mode.
- [ ] Workspace admin/user management works without external IdP dependencies.

## Phase 4: External IAM with OIDC First

**Objective:** Add the first external IAM path without regressing the built-in one.

- [ ] Write a dedicated child plan at `docs/superpowers/plans/2026-05-11-oidc-integration.md`.
- [ ] The child plan must cover:
  - provider configuration model
  - authorization request, callback, nonce/state validation
  - claim/group mapping to platform roles
  - just-in-time user provisioning
  - local-password disablement when external IAM is authoritative
  - logout/session-expiry behavior
  - denial-path and misconfiguration tests
- [ ] Execute the child plan.
- [ ] Verify:
  - at least one OIDC provider can be configured successfully
  - role mappings and JIT provisioning work for new and existing users
  - the local built-in path still works when OIDC is disabled

**Phase 4 exit criteria**

- [ ] External IAM is available with OIDC.
- [ ] Built-in IAM remains available when external IAM is not selected.

## Phase 5: Git-Backed Skill Registry and Distribution

**Objective:** Implement Workstream F with strong trust-boundary validation.

- [ ] Write a dedicated child plan at `docs/superpowers/plans/2026-05-11-git-backed-skill-registry.md`.
- [ ] The child plan must cover:
  - skill source model and manifest schema
  - clone/pull/update jobs and version/ref handling
  - archive validation, safe extraction, and file-size limits
  - local extracted working copies and browsable file tree UI
  - generation or display of AI-facing usage prompts/instructions
  - tests for malicious archives, path traversal, oversized content, and update semantics
- [ ] Execute the child plan.
- [ ] Verify:
  - admins can register a Git source and refresh it safely
  - users can inspect the downloaded tree and AI prompt/instructions
  - hostile or malformed inputs are rejected cleanly

**Phase 5 exit criteria**

- [ ] Skills can be registered from Git, downloaded safely, inspected, and presented with a usable AI prompt.

## Phase 6: Security, Observability, and Release Gates

**Objective:** Complete Workstreams E and G plus the production certification pass from the master plan.

- [ ] Write a dedicated child plan at `docs/superpowers/plans/2026-05-11-security-observability-release-gates.md`.
- [ ] The child plan must cover:
  - CI gates for unit/integration tests, lint/type checks, dependency scanning, image scanning, and secret detection
  - structured logs, key metrics, and alert hooks
  - audit visibility for admin-sensitive actions
  - threat-model docs for control plane, tool gateway, runtime, and skill ingestion
  - validation coverage for access control, auth/session weaknesses, SSRF, archive injection, unsafe deserialization, CSRF where applicable, and abuse/rate-limit paths
  - backup, restore, and upgrade runbooks plus drills
- [ ] Execute the child plan.
- [ ] Verify:
  - CI blocks releases when critical gates fail
  - production diagnostics expose enough signal to operate the stack confidently
  - threat-model docs and runbooks exist alongside tested verification procedures

**Phase 6 exit criteria**

- [ ] Releases are blocked on failed tests, failed scans, or critical vulnerabilities.
- [ ] Operators have documented backup, restore, upgrade, and troubleshooting procedures.
- [ ] The system exposes logs/metrics/audit trails sufficient for production support.

## Final Certification Pass

- [ ] Run the full test/build/security suite defined by the earlier phases from a fresh checkout in a clean worktree.
- [ ] Perform a documented operator walkthrough:
  - deploy from docs with no code edits
  - hit bootstrap mode on first launch
  - complete setup
  - authenticate via built-in IAM
  - authenticate via OIDC if configured
  - register and inspect a Git-backed skill
  - run a manual job and a scheduled job
- [ ] Record any gaps against the master-plan acceptance criteria and either:
  - fix them immediately, or
  - add a short dated follow-up plan with explicit defer rationale

## Done Definition

The production-readiness master plan is executable to completion when:

- [ ] Phase 0 through Phase 6 have all passed their exit criteria.
- [ ] Every phase has either a shipped implementation or an explicit dated follow-up plan file.
- [ ] The master-plan acceptance criteria have all been demonstrated from a fresh self-hosted deployment.
