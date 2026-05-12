# Git-Backed Skill Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or equivalent task-by-task execution. This plan is the dedicated child plan required by Phase 5 of `2026-05-11-production-readiness-execution-checklist.md`.

**Goal:** Let admins register a Git-backed automation or skill source, refresh it safely, inspect the extracted file tree, and present AI-facing instructions without introducing a second runtime model beside the existing agent/version/catalog pipeline.

**Architecture:** Treat Git-backed skills as source records that feed the current `Agent` and `AgentVersion` deployment path. A source sync clones a pinned Git ref into a temporary directory, validates the tree and manifest using the existing package descriptor rules, extracts or derives AI-facing instructions, snapshots a safe file tree for browsing, stores an extracted working copy under a controlled registry root, and then deploys the package through the existing build and inspection path so catalog/installations continue to work unchanged.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, local `git` CLI invocation, existing package descriptor and deploy services, Next.js 14 app router, pytest integration coverage with local temporary Git repositories

---

## Assumptions Locked For This Plan

- A Git-backed skill is still an automation package described by `automation.yaml` or legacy `agent.yaml`; the registry does not invent a second manifest format.
- This phase supports one source per registered slug per tenant. Refreshing the same source should update metadata and produce a new `AgentVersion` rather than duplicate the agent.
- The first supported transport is standard Git clone via local `git`. HTTPS and local file-backed repositories are allowed; SSH-specific ergonomics can be deferred if they complicate testing or operator setup.
- The registry stores extracted working copies on disk under a configured root owned by the control plane. The UI reads a sanitized tree snapshot from the database rather than walking arbitrary filesystem paths directly.
- Prompt or instruction display prefers `AI_INSTRUCTIONS.md`, then `SKILL.md`, then `README.md`, then a descriptor-derived fallback summary. This keeps the initial UX useful even when authors do not provide a dedicated prompt file.
- Archive and extraction safety still matter even though the source is Git-backed: the implementation must enforce path normalization, deny `.git` contents in surfaced trees, apply per-file and total-size limits, and reject dangerous or oversized content cleanly.
- This phase reuses the current agent deploy pipeline wherever practical. If a helper must be split out from `agent_deploy_service` to support directory-based deploy, do that instead of duplicating build logic.

## File Structure

**Create:**
- `services/control-plane/app/models/skill_source.py`
- `services/control-plane/app/schemas/skill_registry.py`
- `services/control-plane/app/services/skill_registry_service.py`
- `services/control-plane/app/api/skill_registry.py`
- `services/control-plane/alembic/versions/0008_git_skill_registry.py`
- `tests/unit/test_skill_registry_service.py`
- `tests/integration/test_skill_registry_admin_api.py`
- `tests/integration/test_skill_registry_view_api.py`
- `frontend/app/admin/skills/page.tsx`
- `frontend/app/app/skills/page.tsx`
- `frontend/app/app/skills/[slug]/page.tsx`
- `frontend/components/SkillRegistryPanel.tsx`
- `frontend/components/SkillTreeBrowser.tsx`

**Modify:**
- `services/control-plane/app/models/__init__.py`
- `services/control-plane/app/main.py`
- `services/control-plane/app/core/config.py`
- `services/control-plane/app/api/admin.py`
- `services/control-plane/app/api/catalog.py`
- `services/control-plane/app/services/agent_deploy_service.py`
- `services/control-plane/app/services/package_descriptor.py`
- `services/control-plane/app/services/installations_service.py`
- `frontend/app/admin/layout.tsx`
- `frontend/components/PlatformDocs.tsx`
- `frontend/lib/api.ts`
- `frontend/lib/types.ts`
- `docs/self-hosting.md`

## Task 1: Add Skill Source Model, Storage Root, And Metadata Snapshot

**Files:**
- Create: `services/control-plane/app/models/skill_source.py`
- Modify: `services/control-plane/app/models/__init__.py`
- Modify: `services/control-plane/app/core/config.py`
- Create: `services/control-plane/alembic/versions/0008_git_skill_registry.py`

- [ ] Add a `SkillSource` model with at least:
  - `id`, `tenant_id`, `slug`, `display_name`
  - `repo_url`, `git_ref`, `resolved_commit_sha`
  - `status` enum such as `pending`, `ready`, `error`
  - `descriptor_format`, `manifest_json`
  - `tree_json` for the sanitized browsable file tree
  - `instructions_markdown`
  - `extracted_root`
  - `last_synced_at`, `last_error`
  - `created_by`, `created_at`, `updated_at`
- [ ] Add a config setting for the registry storage root, for example `SKILL_REGISTRY_ROOT`, with a development-safe default.
- [ ] Create Alembic migration `0008_git_skill_registry.py` for the new table and indexes.
- [ ] Enforce uniqueness on `(tenant_id, slug)` so refresh updates the same source record instead of duplicating it.

**Verification**

Run:

```powershell
$env:PYTHONPATH="services/control-plane;packages/platform_sdk;packages/platform_cli"
py -3.13 -m pytest tests/unit/test_skill_registry_service.py -q
```

Expected: import/model-level coverage passes once Task 2 lands.

## Task 2: Implement Git Sync, Safe Tree Validation, And Instruction Resolution

**Files:**
- Create: `services/control-plane/app/services/skill_registry_service.py`
- Modify: `services/control-plane/app/services/agent_deploy_service.py`
- Modify: `services/control-plane/app/services/package_descriptor.py`
- Create: `tests/unit/test_skill_registry_service.py`

- [ ] Implement `sync_skill_source(...)` that:
  - clones the requested repository into a temp directory
  - checks out the requested ref and records the resolved commit SHA
  - validates the repo contains a top-level `automation.yaml` or `agent.yaml`
  - enforces total-size, per-file-size, and file-count limits before persisting anything
  - builds a sanitized tree snapshot excluding `.git` and other internal noise
  - resolves AI-facing instructions from `AI_INSTRUCTIONS.md`, `SKILL.md`, `README.md`, or descriptor fallback
  - copies the validated working tree into the registry root under a deterministic per-source location
- [ ] Split or reuse deploy helpers so the cloned tree can feed the existing `Agent` and `AgentVersion` path without duplicating Docker build or inspection logic.
- [ ] Unit tests must cover:
  - path and size validation
  - instruction-file precedence
  - tree snapshot sanitization
  - resolved commit SHA capture
  - manifest validation failure for missing descriptors

**Verification**

Run:

```powershell
$env:PYTHONPATH="services/control-plane;packages/platform_sdk;packages/platform_cli"
py -3.13 -m pytest tests/unit/test_skill_registry_service.py -q
```

Expected: PASS

## Task 3: Add Admin Registry APIs For Register, Refresh, And Browse

**Files:**
- Create: `services/control-plane/app/schemas/skill_registry.py`
- Create: `services/control-plane/app/api/skill_registry.py`
- Modify: `services/control-plane/app/main.py`
- Create: `tests/integration/test_skill_registry_admin_api.py`

- [ ] Add admin-only endpoints to:
  - list registered sources
  - register or update a source by `repo_url` and `git_ref`
  - refresh an existing source
  - fetch source detail including tree snapshot, instruction text, and current sync status
- [ ] Registration and refresh should:
  - call the sync service
  - update the `SkillSource` metadata
  - deploy or update the backing `AgentVersion`
  - return structured sync status and any validation errors
- [ ] Integration tests must cover:
  - register a source from a local temporary Git repo
  - refresh after a new commit and observe updated commit SHA/version
  - non-admin access returns 403
  - oversized or malformed repos are rejected cleanly

**Verification**

Run:

```powershell
$env:PYTHONPATH="services/control-plane;packages/platform_sdk;packages/platform_cli"
py -3.13 -m pytest tests/integration/test_skill_registry_admin_api.py -q
```

Expected: PASS

## Task 4: Add User-Facing Inspection Surfaces

**Files:**
- Modify: `services/control-plane/app/api/catalog.py`
- Create: `tests/integration/test_skill_registry_view_api.py`
- Create: `frontend/app/admin/skills/page.tsx`
- Create: `frontend/app/app/skills/page.tsx`
- Create: `frontend/app/app/skills/[slug]/page.tsx`
- Create: `frontend/components/SkillRegistryPanel.tsx`
- Create: `frontend/components/SkillTreeBrowser.tsx`
- Modify: `frontend/app/admin/layout.tsx`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/lib/types.ts`

- [ ] Add app-facing read endpoints or enrich existing catalog detail so users can inspect:
  - the registered source metadata
  - the sanitized file tree
  - AI-facing instructions or prompt text
  - current deployed version and sync status
- [ ] Add an admin page for source registration and refresh actions.
- [ ] Add a user page for read-only browsing and prompt viewing.
- [ ] Keep the UI simple but production-usable: searchable tree, prompt panel, clear sync status, and safe error states.
- [ ] Integration coverage should prove a registered source becomes visible for inspection without exposing filesystem internals.

**Verification**

Run:

```bash
npm --prefix frontend run build
```

Expected: PASS, including the new admin and app skill pages

## Task 5: Document Operator Flow And Final Phase Verification

**Files:**
- Modify: `docs/self-hosting.md`
- Modify: `frontend/components/PlatformDocs.tsx`

- [ ] Document how an operator registers a Git-backed source, what repository shape is required, where instructions are read from, and what sync errors mean.
- [ ] Document the trust boundary and current limits:
  - supported Git transports
  - size limits
  - what gets deployed automatically
  - what is intentionally deferred
- [ ] Update in-app docs so admins and users can discover the feature without reading repo docs first.

**Verification**

Run:

```powershell
$env:PYTHONPATH="services/control-plane;packages/platform_sdk;packages/platform_cli"
py -3.13 -m pytest tests/unit/test_skill_registry_service.py tests/integration/test_skill_registry_admin_api.py tests/integration/test_skill_registry_view_api.py -q
npm --prefix frontend run build
docker compose -f docker-compose.yml -f docker-compose.prod.yml config
```

Expected: PASS

## Commit Boundary

- Commit 1: plan + model/migration/storage root
- Commit 2: sync service and deploy integration
- Commit 3: admin APIs and tests
- Commit 4: user inspection APIs and frontend
- Commit 5: docs and final verification
