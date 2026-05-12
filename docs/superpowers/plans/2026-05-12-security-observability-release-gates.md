# Security, Observability, Release Gates, and Certification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the remaining production-readiness work after Phase 5 by adding enforceable CI and security gates, structured logs and basic metrics, operator runbooks, and a fresh-deployment certification path.

**Architecture:** Keep the current FastAPI, Next.js, Docker Compose, and RQ architecture intact, and add release discipline around it instead of reshaping the product again. The implementation should centralize observability primitives in shared helpers, add GitHub Actions workflows that exercise the same local verification commands maintainers use, and document a single operator path from deploy to certification.

**Tech Stack:** GitHub Actions, FastAPI, SQLAlchemy, structlog, Prometheus text-format metrics, pytest, Next.js build checks, Docker Compose config validation, Trivy, Gitleaks, pip-audit, npm audit

---

## File Structure

**Create:**
- `.github/workflows/ci.yml`
- `.github/workflows/security.yml`
- `services/control-plane/app/core/logging.py`
- `services/tool-gateway/app/logging.py`
- `services/control-plane/app/api/metrics.py`
- `services/control-plane/app/schemas/audit.py`
- `tests/unit/test_logging_config.py`
- `tests/unit/test_metrics_endpoint.py`
- `tests/unit/test_agent_deploy_service.py`
- `tests/integration/test_admin_audit_feed.py`
- `tests/integration/test_bootstrap_production_readiness.py`
- `docs/runbooks/backup-restore.md`
- `docs/runbooks/upgrade.md`
- `docs/runbooks/production-certification.md`
- `docs/threat-models/control-plane.md`
- `docs/threat-models/tool-gateway.md`
- `docs/threat-models/runtime.md`
- `docs/threat-models/skill-ingestion.md`
- `scripts/certify-production.ps1`

**Modify:**
- `README.md`
- `docs/self-hosting.md`
- `docker-compose.prod.yml`
- `services/control-plane/pyproject.toml`
- `services/control-plane/app/main.py`
- `services/control-plane/app/api/admin.py`
- `services/control-plane/app/worker.py`
- `services/control-plane/app/scheduler.py`
- `services/tool-gateway/app/main.py`
- `services/tool-gateway/app/config.py`
- `services/tool-gateway/app/tools/http.py`
- `services/control-plane/app/services/agent_deploy_service.py`
- `frontend/components/PlatformDocs.tsx`

## Task 1: Add Baseline CI Gates For Backend, Frontend, And Compose Validation

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `README.md`

- [ ] **Step 1: Create the CI workflow file**

```yaml
name: ci

on:
  push:
    branches: ["main", "codex/**"]
  pull_request:

jobs:
  backend-and-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - name: Install backend deps
        run: pip install -e services/control-plane -e packages/platform_sdk -e packages/platform_cli
      - name: Install frontend deps
        run: npm --prefix frontend ci
      - name: Backend unit tests
        run: pytest tests/unit/test_schedule_service.py tests/unit/test_runtime_security_settings.py tests/unit/test_skill_registry_service.py -q
      - name: Frontend production build
        run: npm --prefix frontend run build
      - name: Compose config validation
        run: docker compose -f docker-compose.yml -f docker-compose.prod.yml config
```

- [ ] **Step 2: Run a local dry-check against the new workflow assumptions**

Run: `npm --prefix frontend run build`
Expected: PASS

Run: `py -3.13 -m pytest tests/unit/test_schedule_service.py tests/unit/test_runtime_security_settings.py tests/unit/test_skill_registry_service.py -q`
Expected: PASS

- [ ] **Step 3: Document the new baseline gate in the README**

```md
## CI gates

Every branch is expected to pass:

- backend unit tests
- frontend production build
- compose production config validation

These same checks run in `.github/workflows/ci.yml`.
```

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml README.md
git commit -m "ci: add baseline build and test gates"
```

## Task 2: Add Security Scanning And Secret-Detection Workflows

**Files:**
- Create: `.github/workflows/security.yml`
- Modify: `services/control-plane/pyproject.toml`

- [ ] **Step 1: Create the security workflow**

```yaml
name: security

on:
  push:
    branches: ["main", "codex/**"]
  pull_request:
  schedule:
    - cron: "0 2 * * *"

jobs:
  scans:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - name: Install backend deps
        run: pip install -e services/control-plane -e packages/platform_sdk -e packages/platform_cli pip-audit
      - name: Install frontend deps
        run: npm --prefix frontend ci
      - name: Python dependency audit
        run: pip-audit
      - name: npm audit
        run: npm --prefix frontend audit --audit-level=high
      - name: Gitleaks
        uses: gitleaks/gitleaks-action@v2
      - name: Trivy repo scan
        uses: aquasecurity/trivy-action@0.24.0
        with:
          scan-type: fs
          scan-ref: .
          format: table
          exit-code: "1"
          severity: CRITICAL,HIGH
```

- [ ] **Step 2: Add any backend dependency pinning needed to stabilize audits**

```toml
[project.optional-dependencies]
dev = [
  "pip-audit>=2.8",
]
```

- [ ] **Step 3: Verify the security tools can run locally where available**

Run: `pip install pip-audit`
Expected: PASS

Run: `pip-audit`
Expected: PASS or actionable dependency findings that must be fixed before merge

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/security.yml services/control-plane/pyproject.toml
git commit -m "ci: add security scanning workflow"
```

## Task 3: Add Structured Logging, Metrics, And Admin Audit Visibility

**Files:**
- Create: `services/control-plane/app/core/logging.py`
- Create: `services/tool-gateway/app/logging.py`
- Create: `services/control-plane/app/api/metrics.py`
- Create: `services/control-plane/app/schemas/audit.py`
- Modify: `services/control-plane/app/main.py`
- Modify: `services/control-plane/app/api/admin.py`
- Modify: `services/control-plane/app/worker.py`
- Modify: `services/control-plane/app/scheduler.py`
- Modify: `services/tool-gateway/app/main.py`
- Create: `tests/unit/test_logging_config.py`
- Create: `tests/unit/test_metrics_endpoint.py`
- Create: `tests/integration/test_admin_audit_feed.py`

- [ ] **Step 1: Add a shared control-plane logging helper**

```python
import logging
import structlog

def configure_logging(service_name: str) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )
```

- [ ] **Step 2: Wire the logging helper into HTTP services and long-running workers**

```python
from app.core.logging import configure_logging

configure_logging("control-plane")
```

```python
from app.logging import configure_logging

configure_logging("tool-gateway")
```

- [ ] **Step 3: Add a minimal Prometheus-style metrics endpoint**

```python
from fastapi import APIRouter, Response

router = APIRouter(tags=["metrics"])

@router.get("/metrics")
def metrics() -> Response:
    body = "\n".join([
        "# HELP platform_health Always 1 when the process is serving requests",
        "# TYPE platform_health gauge",
        "platform_health 1",
    ]) + "\n"
    return Response(content=body, media_type="text/plain; version=0.0.4")
```

- [ ] **Step 4: Add an admin audit feed endpoint**

```python
@router.get("/audit")
def list_audit_events(actor: AdminOnly, db: DbSession) -> list[AuditEventPublic]:
    rows = db.execute(
        select(AuditLog)
        .where(AuditLog.tenant_id == actor.tenant_id)
        .order_by(AuditLog.created_at.desc())
        .limit(100)
    ).scalars().all()
    return [AuditEventPublic.model_validate(row) for row in rows]
```

- [ ] **Step 5: Add focused tests**

Run: `py -3.13 -m pytest tests/unit/test_logging_config.py tests/unit/test_metrics_endpoint.py tests/integration/test_admin_audit_feed.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add services/control-plane/app/core/logging.py services/tool-gateway/app/logging.py services/control-plane/app/api/metrics.py services/control-plane/app/api/admin.py services/control-plane/app/main.py services/control-plane/app/worker.py services/control-plane/app/scheduler.py services/tool-gateway/app/main.py services/control-plane/app/schemas/audit.py tests/unit/test_logging_config.py tests/unit/test_metrics_endpoint.py tests/integration/test_admin_audit_feed.py
git commit -m "feat: add structured logs metrics and audit feed"
```

## Task 4: Add Security Regression Tests And Operator Runbooks

**Files:**
- Create: `tests/unit/test_agent_deploy_service.py`
- Modify: `services/tool-gateway/app/tools/http.py`
- Modify: `services/control-plane/app/services/agent_deploy_service.py`
- Create: `docs/runbooks/backup-restore.md`
- Create: `docs/runbooks/upgrade.md`
- Create: `docs/threat-models/control-plane.md`
- Create: `docs/threat-models/tool-gateway.md`
- Create: `docs/threat-models/runtime.md`
- Create: `docs/threat-models/skill-ingestion.md`
- Modify: `docs/self-hosting.md`

- [ ] **Step 1: Add explicit archive-validation unit tests for deploy safety**

```python
def test_safe_extract_rejects_parent_traversal() -> None:
    payload = make_zip({"../escape.txt": "boom"})
    with pytest.raises(DeployError, match="unsafe path"):
        _safe_extract(payload, tmp_path)
```

- [ ] **Step 2: Add or tighten SSRF and allowlist tests around the HTTP tool**

```python
def test_http_tool_rejects_url_not_in_allowlist() -> None:
    with pytest.raises(HTTPException):
        enforce_http_allowlist(["https://allowed.example"], "https://evil.example")
```

- [ ] **Step 3: Write operator runbooks with executable checks**

```md
## Backup

```bash
docker compose exec postgres pg_dump -U platform platform > platform.sql
```

## Restore

```bash
cat platform.sql | docker compose exec -T postgres psql -U platform -d platform
```
```

- [ ] **Step 4: Write one threat model per major boundary**

```md
## Assets
- tenant data
- encrypted secrets
- run tokens

## Trust boundaries
- browser to frontend
- control plane to worker
- agent container to tool gateway
```

- [ ] **Step 5: Verify the regression tests**

Run: `py -3.13 -m pytest tests/unit/test_agent_deploy_service.py tests/unit/test_runtime_security_settings.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/unit/test_agent_deploy_service.py services/tool-gateway/app/tools/http.py services/control-plane/app/services/agent_deploy_service.py docs/runbooks/backup-restore.md docs/runbooks/upgrade.md docs/threat-models/control-plane.md docs/threat-models/tool-gateway.md docs/threat-models/runtime.md docs/threat-models/skill-ingestion.md docs/self-hosting.md
git commit -m "docs: add production runbooks and threat models"
```

## Task 5: Add A Fresh-Deployment Certification Script And Final Docs Alignment

**Files:**
- Create: `scripts/certify-production.ps1`
- Create: `docs/runbooks/production-certification.md`
- Modify: `README.md`
- Modify: `frontend/components/PlatformDocs.tsx`
- Create: `tests/integration/test_bootstrap_production_readiness.py`

- [ ] **Step 1: Add a certification script that codifies the operator checks**

```powershell
$ErrorActionPreference = "Stop"
npm --prefix frontend run build
$env:PYTHONPATH="services/control-plane;packages/platform_sdk;packages/platform_cli"
py -3.13 -m pytest tests/unit/test_schedule_service.py tests/unit/test_runtime_security_settings.py tests/unit/test_skill_registry_service.py -q
docker compose -f docker-compose.yml -f docker-compose.prod.yml config | Out-Null
Write-Host "Local certification checks passed."
```

- [ ] **Step 2: Add an integration test for fresh-instance bootstrap expectations**

```python
def test_production_bootstrap_blocks_normal_routes_until_complete(client: TestClient) -> None:
    response = client.get("/admin/whoami")
    assert response.status_code == 423
    assert response.json()["bootstrap_required"] is True
```

- [ ] **Step 3: Document the certification walkthrough**

```md
1. Launch the production overlay.
2. Complete `/setup`.
3. Verify built-in IAM or OIDC login.
4. Register a Git-backed skill source.
5. Approve the pending agent version.
6. Run one manual job and one scheduled job.
```

- [ ] **Step 4: Reconcile README and in-app docs with the shipped behavior**

```md
- CI and security workflows gate every push and pull request.
- Metrics and audit feeds are available to operators.
- Backup, restore, and upgrade runbooks live under `docs/runbooks/`.
```

- [ ] **Step 5: Final verification**

Run: `py -3.13 -m pytest tests/unit/test_logging_config.py tests/unit/test_metrics_endpoint.py tests/unit/test_agent_deploy_service.py tests/integration/test_admin_audit_feed.py tests/integration/test_bootstrap_production_readiness.py -q`
Expected: PASS

Run: `npm --prefix frontend run build`
Expected: PASS

Run: `docker compose -f docker-compose.yml -f docker-compose.prod.yml config`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/certify-production.ps1 docs/runbooks/production-certification.md README.md frontend/components/PlatformDocs.tsx tests/integration/test_bootstrap_production_readiness.py
git commit -m "chore: add production certification workflow"
```

## Self-Review

- Spec coverage: this plan covers CI gates, security scanning, structured logging, metrics, audit visibility, threat models, runbooks, and the fresh-deployment certification pass.
- Placeholder scan: no `TODO`, `TBD`, or “similar to earlier task” placeholders remain.
- Type consistency: route and helper names are consistent with the current FastAPI layout (`app.main`, `app.api.admin`, `tool-gateway/app/main.py`).

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-12-security-observability-release-gates.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints
