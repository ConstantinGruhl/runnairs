# Open Automation Platform Handoff

Date: 2026-05-10

## Purpose

This document is a handoff artifact for the next AI session. It captures:

- the current verified baseline of the repository
- the desired product direction
- the architectural changes needed to get there
- the major gaps between current and target state
- a phased roadmap that can be turned into a separate implementation plan

This handoff is intentionally written against the current repository state, not an earlier snapshot.

## Product Direction

The platform should evolve from a local prototype for governed AI agents into a free, MIT-licensed, self-hostable automation platform that companies can run on their own infrastructure.

The target product is:

- open-source and easy to self-host
- usable as a company's central place for automation
- AI-native, but not limited to AI-only workflows
- able to install and run automations built by other people
- able to expose what secrets, API keys, connections, approvals, triggers, and optional expansions an automation needs
- able to let admins enable or disable optional expansions from the UI
- able to support multiple interaction surfaces such as Teams, WhatsApp, Slack, email, webhooks, and future channels
- governed through permissions, audit logs, approvals, tenant scoping, and safe execution

The product should become the engine that lets companies connect tools, orchestrate workflows, and add AI reasoning where useful.

## Current Verified Baseline

### Core platform

The repository already provides a strong prototype foundation:

- a multi-service Docker Compose stack in `docker-compose.yml`
- a FastAPI control plane in `services/control-plane/app/main.py`
- a FastAPI tool gateway in `services/tool-gateway/app/main.py`
- a Docker-based isolated execution backend in `services/control-plane/app/execution/docker_backend.py`
- a Python SDK in `packages/platform_sdk/platform_sdk/`
- a developer CLI in `packages/platform_cli/platform_cli/main.py`
- a Next.js frontend in `frontend/`

### Governance and safety primitives

The current platform already has:

- tenant-aware users and roles: `admin`, `developer`, `user`
- workspace secrets and user-scoped secrets
- encrypted secret storage
- per-agent manifest permissions
- tool allowlists
- HTTP allowlists
- approval-gated actions
- audit-log writes on tool calls

Relevant files:

- `services/control-plane/app/api/auth.py`
- `services/control-plane/app/api/secrets.py`
- `services/control-plane/app/api/me.py`
- `services/control-plane/app/services/secret_store.py`
- `services/tool-gateway/app/policy.py`
- `services/tool-gateway/app/audit.py`
- `services/tool-gateway/app/tools/http.py`

### Runtime and orchestration

The current platform supports:

- manual runs
- approval pauses
- feedback submission
- cron-based scheduling

Relevant files:

- `services/control-plane/app/api/runs.py`
- `services/control-plane/app/api/approvals.py`
- `services/control-plane/app/api/feedback.py`
- `services/control-plane/app/api/schedules.py`
- `services/control-plane/app/scheduler.py`
- `services/control-plane/app/models/run.py`
- `services/control-plane/app/models/feedback.py`
- `services/control-plane/app/models/schedule.py`

### Frontend capabilities

The current UI already exposes:

- login and role-based landing areas
- app catalog with declared inputs, tools, and approval requirements
- connected user accounts for user-scoped secrets
- run detail with polling and approval actions
- feedback widget
- developer schedule management
- developer feedback visibility

Relevant files:

- `frontend/app/app/agents/[slug]/page.tsx`
- `frontend/app/app/runs/[id]/page.tsx`
- `frontend/app/dev/agents/[slug]/page.tsx`
- `frontend/components/ConnectedAccounts.tsx`
- `frontend/components/FeedbackWidget.tsx`
- `frontend/components/ScheduleManager.tsx`

### Current automation packaging model

Today, automations are packaged as agent folders with:

- `agent.yaml`
- `main.py`
- optional tests

The manifest already declares:

- name and description
- inputs
- tools
- secrets
- approval requirements
- limits
- HTTP allowlist

Relevant examples:

- `examples/weekly-summary/agent.yaml`
- `examples/inbox-triage/agent.yaml`
- `examples/customer-briefing/agent.yaml`

This is important: the current manifest model already gives the UI enough information to show some required setup. The next version should build on this pattern, not throw it away.

### Tests and documentation

The repo has meaningful tests and a platform skill:

- agent unit tests under `examples/*/tests/`
- integration flow test in `tests/integration/test_happy_path.py`
- developer guidance in `skills/platform-agent/SKILL.md`

## Current Constraints and Gaps

### Product-shape gap

The current system is still framed as an agent platform. To become the company's central automation engine, it needs to support both:

- free-form AI-powered automations
- more structured workflow automations with reusable modules and channels

The core abstraction needs to move from "run an agent" toward "install and operate an automation package with optional capabilities."

### Self-hosting and production gap

The repo is still local-prototype oriented:

- the frontend container runs development mode in `frontend/Dockerfile`
- the stack is tied to `localhost`
- MailHog and mock CRM are demo dependencies
- the control plane and worker rely on the host Docker socket

This is good for local prototyping but not yet good enough for a clean production deployment story.

### Identity gap

Auth is still local email/password plus JWTs. There is no:

- OIDC
- SAML
- SCIM
- JIT provisioning
- group-to-role mapping
- enterprise SSO admin setup flow

### Connection and plugin gap

The current system uses secrets as the main integration model. That works for the prototype, but it is not enough for installable third-party automations and UI-activated expansions.

The platform needs first-class concepts for:

- provider plugins
- connections
- scopes
- OAuth flows
- connection health
- required scopes and fields
- activation state

### Runtime contract gap

There is not yet a formal, stable contract for:

- optional modules inside an automation
- declaring channel expansions such as Teams or WhatsApp
- letting the platform know which expansions exist
- enabling or disabling those expansions in the UI
- verifying that code and manifest stay aligned

### Marketplace and trust gap

To support "other people's automations," the platform needs:

- installable package format
- compatibility/version checks
- install review UI
- permission review
- required connection review
- optional module review
- version pinning and upgrade flow

## Target Product Shape

The platform should become an open automation control plane with AI as one capability inside it.

The recommended target model is:

- **automation packages** are installable units
- **provider plugins** are platform-level integrations such as Teams, Slack, WhatsApp, GitHub, Notion, Salesforce
- **automation modules** are optional features inside a package, such as a Teams channel output, WhatsApp delivery, or knowledge sync
- **connections** are managed auth/config objects for providers
- **activations** capture which optional modules are enabled for a given automation installation

This lets the UI answer:

- What does this automation do?
- What is required to make it run?
- Which optional expansions exist?
- Which provider plugins do they depend on?
- Which keys, tokens, scopes, or OAuth connections are missing?
- Which modules are enabled or disabled right now?

## Recommended Architecture

### 1. Evolve `agent.yaml` into a richer package descriptor

Introduce a new descriptor, preferably `automation.yaml`, while keeping backwards compatibility with `agent.yaml` during migration.

The descriptor should define:

- package metadata
- version
- install summary
- human-readable setup instructions
- inputs and outputs
- triggers
- required tools and permissions
- required approvals
- required workspace connections
- required user connections
- optional automation modules
- optional provider dependencies
- configuration schema for each module
- compatibility requirements

The platform should continue to expose this data in the UI before a run starts.

### 2. Separate provider plugins from automation modules

Do not use one overloaded "plugin" concept.

Use:

- **ProviderPlugin** for reusable platform integrations
- **AutomationModule** for optional features inside an automation package

Example:

- Provider plugins:
  - `microsoft_teams`
  - `whatsapp_business`
  - `slack`
  - `notion`
  - `confluence`
- Optional modules inside a knowledge-base automation:
  - `teams_channel_delivery`
  - `whatsapp_delivery`
  - `daily_digest`
  - `kb_sync`

Each module should declare:

- module ID
- title
- description
- whether it is optional or required
- which provider plugins it depends on
- which connections it needs
- which settings it needs

### 3. Make the platform-to-automation contract manifest-first

The platform should not depend on a live automation container just to discover which expansions exist.

Recommended model:

- the package descriptor is the source of truth for platform-visible capabilities
- package deploy performs a validation step that checks the code implements the declared modules and handlers
- runtime only receives the enabled modules and resolved connection references

This is the safest and most UI-friendly approach.

### 4. Add a deploy-time inspection handshake

There should still be a formal communication path between code and platform.

Recommended approach:

- during deploy, the platform builds or inspects the package in a controlled environment
- the SDK exposes an inspection command such as `platform-sdk inspect`
- the inspection result reports:
  - declared handlers
  - module IDs implemented by the code
  - trigger entrypoints
  - supported channels
  - declared compatibility version
- deploy fails if the manifest and code disagree

This creates the needed communication between the automation package and the platform without making runtime discovery fragile.

### 5. Introduce first-class Connection objects

Replace "paste secrets by name" as the main long-term integration model.

A Connection should represent:

- provider type
- auth type
- workspace or user scope
- secret fields
- OAuth tokens and refresh state
- granted scopes
- connection health
- last validated time
- display metadata

The UI should be able to show:

- which connections are required
- which are already configured
- what permissions/scopes are needed
- whether re-auth is required

### 6. Add an installation and activation flow

Installation should become a first-class lifecycle:

1. upload or install an automation package
2. inspect descriptor and code
3. show required permissions, tools, and connections
4. show optional modules and channel expansions
5. let admin enable desired modules
6. guide admin through required connection setup
7. validate readiness
8. activate the automation

This flow is a better fit for third-party automation reuse than the current developer-only deploy mental model.

### 7. Pass activation state into runtime explicitly

At runtime, the automation should not guess what is enabled.

The control plane should pass:

- enabled module IDs
- resolved connection references
- tenant-level config
- trigger context
- user context when relevant

The SDK should expose helpers such as:

- `ctx.module_enabled("teams_channel_delivery")`
- `ctx.connection("microsoft_teams")`
- `ctx.installation_config()`

This forces code into platform-visible boundaries.

### 8. Add a UI automation scaffolder

Yes, the platform should support creating a new automation from the UI.

Recommended behavior:

- developer clicks "Create automation"
- UI collects basic metadata
- platform generates a starter folder or repo
- starter includes:
  - `automation.yaml`
  - `main.py`
  - module stubs
  - tests
  - `AI_INSTRUCTIONS.md`
  - README/setup template

This should complement, not replace, the CLI.

The UI scaffolder should follow the same conventions as the CLI so both paths stay aligned.

## Proposed Data Model Additions

The next planning pass should likely introduce entities along these lines:

- `provider_plugin`
- `provider_plugin_version`
- `connection_definition`
- `workspace_connection`
- `user_connection`
- `automation_installation`
- `automation_module`
- `installation_module_state`
- `trigger_definition`
- `webhook_endpoint`
- `activation_event`

Existing entities such as `agent`, `agent_version`, `run`, `schedule`, `approval`, `feedback`, and `audit_log` should either be evolved or gradually renamed depending on migration strategy.

## Backwards Compatibility Strategy

Do not hard-cut away from the current agent model.

Recommended approach:

- keep current `agent.yaml` support
- add a compatibility layer that maps current agent packages into the new automation package model
- treat today's agents as single-package automations with one default module
- only require the richer model for packages that need optional expansions, channels, or advanced install flows

This lowers migration risk and preserves the working examples and tests.

## Phased Roadmap

### Phase A: Productize the current platform

Goal: make the current system cleaner, more deployable, and more stable before expanding the model.

Deliverables:

- production-ready frontend image
- production compose profile and environment story
- install docs for self-hosting
- clearer separation of demo-only services
- baseline observability and admin diagnostics
- explicit compatibility guarantees for current `agent.yaml`

### Phase B: Introduce connections and package metadata

Goal: move from secret-centric setup to connection-centric setup.

Deliverables:

- Connection model and admin/user connection UIs
- richer package descriptor
- package validation and inspection handshake
- UI that shows required setup from package metadata
- migration of current secret-based setup into connection-aware UI

### Phase C: Add provider plugins and module activation

Goal: support optional expansions and installable third-party automations.

Deliverables:

- ProviderPlugin model
- AutomationModule model
- module activation UI
- readiness checks per module
- runtime support for enabled modules and resolved connections
- initial channel plugins such as Teams and WhatsApp abstractions

### Phase D: Improve runtime orchestration

Goal: make the platform robust for real company automation.

Deliverables:

- durable webhook triggers
- stronger schedule semantics
- resume-safe approvals
- retries and idempotency
- richer trigger model
- better failure and recovery handling

### Phase E: Enterprise setup and adoption

Goal: make the platform realistic for company rollout.

Deliverables:

- OIDC SSO
- later SAML and SCIM
- group-to-role mapping
- audit UI
- admin install review
- package upgrade workflow
- starter library of high-value automations

## Immediate Strategic Recommendations

These should guide the next implementation plan:

1. Preserve and extend the current manifest-driven approach instead of replacing it.
2. Promote connections to first-class objects.
3. Separate provider plugins from automation modules.
4. Add deploy-time package inspection so code and metadata stay aligned.
5. Add activation/install lifecycle before building any marketplace-like feature.
6. Keep the current examples working through a compatibility layer.
7. Build the UI scaffolder after the package contract is defined, not before.

## Acceptance Criteria For The Next Major Version

The next major product step should feel complete when all of the following are true:

- a third-party automation package can be installed without reading its source code
- the UI can show required connections, approvals, tools, and optional modules from metadata
- admins can enable and disable optional modules from the UI
- the runtime only receives the modules and connections that are actually activated
- package deploy validates that metadata and code match
- the platform still runs current example agents through compatibility logic
- the self-hosting story is materially cleaner than the current local prototype

## Open Questions For Planning

These should be resolved during the next planning pass:

- Should provider plugins be code shipped with the platform, installable packages, or both?
- Should activation state be per tenant, per environment, or per installation instance?
- Should a package be allowed to define custom frontend configuration forms, or should config remain schema-driven only?
- Should the platform keep the term "agent" in the user-facing product, or reframe everything as "automation" and "installation"?
- What is the target production runtime after Docker-socket local execution: remote builders, Kubernetes jobs, or both?

## Suggested Planning Prompt For The Next AI

Create a detailed implementation plan for evolving this repository from its current manifest-driven AI agent prototype into an open, self-hostable automation platform with:

- backwards compatibility for current `agent.yaml` packages
- a richer `automation.yaml`-style package descriptor
- first-class provider plugins
- first-class connections
- optional automation modules that can be activated in the UI
- deploy-time package inspection and validation
- UI scaffolding for new automations
- a production-oriented self-hosting story
- a phased migration path from today's model to the new one

Base the plan on the current repository state described in this handoff, and explicitly reference the existing code paths that should be preserved, evolved, or replaced.
