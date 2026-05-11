# Production Readiness Master Plan

Execution driver: [2026-05-11-production-readiness-execution-checklist.md](C:\Users\const\OneDrive\Dokumente\NTU\Runnairs\docs\superpowers\plans\2026-05-11-production-readiness-execution-checklist.md)

## Goal

Turn the current local prototype into a self-hostable product where a customer can start one Docker-based deployment, complete a secure first-run setup flow, connect identity, deploy skills and automations, and operate the platform with confidence.

## Reality Check

The target cannot literally be "100% secure." The practical goal is:

- no known critical or high-severity default vulnerabilities
- secure-by-default bootstrap and configuration
- repeatable testing against common classes of attack
- defense in depth across auth, runtime isolation, secrets, networking, supply chain, and observability

## Product Outcome

The production-ready version should support:

- a documented, one-command container deployment path
- first-launch configure mode with a forced setup wizard
- built-in IAM plus external IAM provider integration
- clear in-app documentation and onboarding
- Git-backed skill packaging and retrieval
- strong CI, release, and security verification gates

## Target Architecture

### 1. Self-hosted runtime

- Keep the current control plane, tool gateway, worker, scheduler, Postgres, Redis, and frontend split.
- Replace the current "prototype compose" framing with a supported self-hosting bundle.
- Move frontend-to-API traffic to same-origin proxying or an explicit reverse-proxy layer so browser clients never need Docker-internal hostnames.
- Support a documented ingress pattern with TLS termination, stable public URLs, and health/ready probes.

### 2. First-run configure mode

- On first launch, the platform should detect "not configured" state before normal login.
- Redirect all users to a setup wizard until the instance has:
  - an instance admin
  - a selected IAM mode
  - core security secrets configured
  - storage/database health confirmed
  - mail/notification defaults configured if required
- Persist a simple instance bootstrap state table so the frontend can branch cleanly between setup mode and normal app mode.

### 3. IAM architecture

- Introduce an instance-level auth configuration subsystem.
- Ship two auth modes in phase one:
  - built-in IAM: local admin + workspace user management, password login, MFA roadmap
  - external IAM: OIDC first, SAML second
- Required production behaviors:
  - role mapping from IdP claims/groups to platform roles
  - just-in-time user provisioning
  - tenant/workspace mapping rules
  - login disablement for local passwords when external IAM is authoritative
  - secure logout/session expiry behavior
- Defer advanced SCIM provisioning until after OIDC is stable unless a customer requirement forces it earlier.

### 4. Skill registry and distribution

- Treat a skill as a Git-backed package with:
  - repo URL
  - version/ref
  - manifest metadata
  - local extracted working copy
  - AI-facing usage prompt/template
- Users should be able to:
  - register a skill source
  - pull or refresh a skill bundle from Git
  - inspect the downloaded file tree
  - copy or view a non-technical prompt that explains how to use or implement the skill with the local AI
- Build guardrails around archive validation, safe extraction, content size, and trust boundaries.

### 5. Documentation surface

- Add a dedicated documentation tab in the product for all roles.
- Minimum content:
  - purpose of the platform
  - admin setup flow
  - developer deploy flow
  - user run flow
  - approvals and secrets model
  - troubleshooting and FAQs
  - production deployment notes
- Longer-form operator docs should still live in repo docs and be linked conceptually from the UI copy.

## Workstreams

### Workstream A: Immediate hardening baseline

- Fix current auth and schedule correctness issues.
- Remove browser dependence on Docker-internal API hostnames.
- Enforce strong production secret validation.
- Add regression tests for access control and timezone scheduling.

### Workstream B: Instance bootstrap and setup mode

- Add `instance_settings` / `instance_bootstrap_state` tables.
- Build a setup wizard route set in the frontend.
- Gate standard login and app pages until bootstrap is complete.
- Add secure secret generation guidance and validation.

### Workstream C: IAM subsystem

- Model auth providers, configuration state, and role mappings.
- Implement built-in IAM as the fallback/default.
- Implement OIDC integration with callback handling, nonce/state validation, and claim mapping.
- Add tests for login, callback, role mapping, denial, and local-auth disablement.

### Workstream D: Production deployment story

- Publish a supported compose deployment profile and reference `.env.production`.
- Add database migration, backup, restore, and upgrade runbooks.
- Document ingress/TLS/reverse-proxy examples.
- Add health, readiness, and startup dependency checks.

### Workstream E: Security program

- Add CI gates for:
  - unit and integration tests
  - dependency scanning
  - container image scanning
  - lint/type checks
  - secret detection
- Add routine validation for common vulnerabilities:
  - broken access control
  - auth/session weaknesses
  - SSRF
  - command/archive injection
  - unsafe deserialization
  - CSRF where cookie auth is introduced
  - rate-limit and abuse paths
- Add threat-model docs for control plane, gateway, runtime, and skill ingestion.

### Workstream F: Git-backed skill management

- Define skill source model and manifest.
- Add backend jobs for clone/pull/verify/extract.
- Add UI for browsing installed skills and viewing the AI prompt/instructions.
- Validate size limits, file allowlists/denylists, and update semantics.

### Workstream G: Observability and operations

- Structured logs across all services.
- Metrics for runs, queue depth, tool latency, approval wait time, and scheduler health.
- Error reporting and alert hooks.
- Audit visibility for admin-sensitive actions.

## Recommended Delivery Phases

### Phase 1: Stabilize current product

- land the four confirmed fixes
- add in-app docs tab
- make tests/builds reliable from a fresh checkout
- publish a production baseline README and operator docs

### Phase 2: First-run experience

- add bootstrap state and configure mode
- create setup wizard for admin, secrets, and runtime checks
- prevent normal use before completion

### Phase 3: IAM foundation

- ship built-in IAM as the default production path
- add OIDC integration and role mapping
- add admin auth configuration UI

### Phase 4: Secure skill distribution

- ship Git-backed skill registry
- add downloaded-file browsing and AI prompt generation
- validate ingestion and update safety

### Phase 5: Production hardening and certification pass

- complete vulnerability test matrix
- add backup/restore drills
- add release checklist and documented SLOs
- execute penetration-style review of common web and container threats

## Acceptance Criteria

The platform is production-ready when all of the following are true:

- A new operator can deploy the stack from docs without code changes.
- First launch always enters configure mode until the instance is safely initialized.
- Production mode refuses weak JWT secrets and equivalent unsafe defaults.
- External IAM can be configured with at least one supported provider type.
- The built-in IAM path remains available when external IAM is not desired.
- Skills can be registered from Git, downloaded safely, inspected, and presented with a usable AI prompt.
- The UI contains role-appropriate documentation for purpose, setup, use, and troubleshooting.
- CI blocks releases on failed tests, failed scans, or critical vulnerabilities.
- Common auth, access control, schedule, and proxy regressions are covered by automated tests.

## Near-Term Implementation Recommendation

Execute the work in this order:

1. Immediate code fixes and test harness cleanup
2. In-app docs plus README/self-hosting refresh
3. Bootstrap/configure mode backend state
4. Frontend setup wizard
5. Built-in IAM hardening
6. OIDC integration
7. Git-backed skill registry
8. Security and operations deepening

## Risks

- IAM and first-run bootstrap cut across backend, frontend, and operational assumptions; partial rollout can create lockout risk.
- Git-backed skill ingestion adds a new supply-chain boundary and must be sandboxed carefully.
- Cookie-based/session-based auth migration will likely be needed if the platform moves beyond local-storage tokens.
- The Docker socket runtime is acceptable for the prototype but remains a long-term isolation concern for hardened installations.
