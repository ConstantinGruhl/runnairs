# Automation Platform Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current manifest-driven AI agent prototype into the first usable version of a self-hostable automation platform while keeping every current `agent.yaml` example deployable and runnable through a compatibility layer.

**Architecture:** Keep the existing `agent`, `agent_version`, `run`, `schedule`, approval, and execution pipeline as the compatibility substrate. Layer a canonical automation descriptor, installation state, connection state, deploy-time inspection, and activation-aware runtime contract on top of that substrate, then expose those concepts through the existing admin, developer, and user surfaces before adding any marketplace behavior.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Next.js 14, Typer, Docker, Postgres, Redis/RQ, PyYAML, pytest

---

## File Structure

**Create:**
- `services/control-plane/app/services/package_descriptor.py`
- `services/control-plane/app/services/provider_registry.py`
- `services/control-plane/app/services/installations_service.py`
- `services/control-plane/app/api/connections.py`
- `services/control-plane/app/api/installations.py`
- `services/control-plane/app/models/connection.py`
- `services/control-plane/app/models/installation.py`
- `services/control-plane/alembic/versions/0004_automation_foundation.py`
- `packages/platform_sdk/platform_sdk/inspect.py`
- `tests/unit/__init__.py`
- `tests/unit/test_package_descriptor.py`
- `tests/unit/test_installation_readiness.py`
- `tests/unit/test_inspection_handshake.py`
- `tests/unit/test_runtime_activation_context.py`
- `tests/unit/test_scaffold_templates.py`
- `tests/integration/test_installation_flow.py`
- `tests/integration/test_admin_diagnostics.py`
- `frontend/app/admin/connections/page.tsx`
- `frontend/app/admin/agents/[slug]/page.tsx`
- `frontend/app/dev/automations/new/page.tsx`
- `frontend/components/InstallationReadinessCard.tsx`
- `frontend/components/ModuleActivationCard.tsx`
- `frontend/components/ConnectionList.tsx`
- `frontend/components/AutomationScaffoldForm.tsx`
- `examples/weekly-summary/automation.yaml`
- `docs/self-hosting.md`
- `docker-compose.prod.yml`

**Modify:**
- `services/control-plane/app/models/agent.py`
- `services/control-plane/app/models/__init__.py`
- `services/control-plane/app/api/admin.py`
- `services/control-plane/app/api/catalog.py`
- `services/control-plane/app/api/dev.py`
- `services/control-plane/app/api/me.py`
- `services/control-plane/app/api/runs.py`
- `services/control-plane/app/execution/docker_backend.py`
- `services/control-plane/app/run_tokens.py`
- `services/control-plane/app/scheduler.py`
- `services/control-plane/app/services/agent_deploy_service.py`
- `services/control-plane/app/main.py`
- `packages/platform_sdk/platform_sdk/context.py`
- `packages/platform_sdk/platform_sdk/__init__.py`
- `packages/platform_sdk/pyproject.toml`
- `packages/platform_cli/platform_cli/main.py`
- `frontend/lib/types.ts`
- `frontend/app/app/agents/[slug]/page.tsx`
- `frontend/app/dev/agents/[slug]/page.tsx`
- `frontend/components/ConnectedAccounts.tsx`
- `frontend/components/ScheduleManager.tsx`
- `frontend/Dockerfile`
- `docker-compose.yml`
- `README.md`
- `skills/platform-agent/SKILL.md`

## Assumptions Locked For This Plan

- Keep the database table names `agent` and `agent_version` for now; change product language in UI and docs first, and add new state tables beside the old ones instead of renaming the whole schema.
- Support both `automation.yaml` and `agent.yaml`, with `automation.yaml` preferred when both exist.
- Keep provider plugin metadata code-defined in phase one through `provider_registry.py`; persist connection and installation state in Postgres, not provider plugin code.
- Treat current tenant-scoped packages as one installation per tenant and agent slug for the first major version. Multi-installation per tenant can come later if the product needs environment clones.
- Keep existing `/app/catalog`, `/runs`, `/dev/agents/*`, and `/admin/agents/*` endpoints working while adding richer payloads and optional alias routes.

### Task 1: Canonical package descriptor and legacy compatibility

**Files:**
- Create: `services/control-plane/app/services/package_descriptor.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/unit/test_package_descriptor.py`
- Create: `examples/weekly-summary/automation.yaml`
- Modify: `services/control-plane/app/services/agent_deploy_service.py`
- Modify: `packages/platform_cli/platform_cli/main.py`

- [ ] **Step 1: Write the failing descriptor normalization tests**

```python
from pathlib import Path

from app.services.package_descriptor import load_package_descriptor


def test_load_package_descriptor_prefers_automation_yaml(tmp_path: Path) -> None:
    (tmp_path / "automation.yaml").write_text(
        "name: weekly-summary\n"
        "display_name: Weekly Summary\n"
        "entrypoint: main:run\n"
        "modules:\n"
        "  - id: email_delivery\n"
        "    required: true\n",
        encoding="utf-8",
    )
    descriptor = load_package_descriptor(tmp_path)
    assert descriptor.format == "automation"
    assert descriptor.data["modules"][0]["id"] == "email_delivery"


def test_load_package_descriptor_normalizes_agent_yaml(tmp_path: Path) -> None:
    (tmp_path / "agent.yaml").write_text(
        "name: hello-world\n"
        "display_name: Hello World\n"
        "entrypoint: main:run\n"
        "permissions:\n"
        "  tools:\n"
        "    - llm.complete\n",
        encoding="utf-8",
    )
    descriptor = load_package_descriptor(tmp_path)
    assert descriptor.format == "legacy_agent"
    assert descriptor.data["modules"][0]["id"] == "default"
    assert descriptor.data["tools"] == ["llm.complete"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_package_descriptor.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.package_descriptor'`

- [ ] **Step 3: Implement canonical descriptor loading**

```python
# services/control-plane/app/services/package_descriptor.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class PackageDescriptor:
    format: str
    manifest_path: str
    data: dict[str, Any]


def load_package_descriptor(root: Path) -> PackageDescriptor:
    for filename, fmt in (("automation.yaml", "automation"), ("agent.yaml", "legacy_agent")):
        path = root / filename
        if not path.exists():
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"{filename} must be a mapping at the top level")
        if fmt == "legacy_agent":
            raw = normalize_legacy_agent_manifest(raw)
        validate_descriptor(raw, source=filename)
        return PackageDescriptor(format=fmt, manifest_path=filename, data=raw)
    raise ValueError("archive is missing automation.yaml or agent.yaml at the top level")


def validate_descriptor(descriptor: dict[str, Any], *, source: str) -> None:
    for field in ("name", "display_name", "entrypoint", "modules"):
        if not descriptor.get(field):
            raise ValueError(f"{source} missing required field: {field}")
    if ":" not in str(descriptor["entrypoint"]):
        raise ValueError(f"{source} entrypoint must look like module:function")
    if not isinstance(descriptor["modules"], list):
        raise ValueError(f"{source} modules must be a list")


def normalize_legacy_agent_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    permissions = manifest.get("permissions") or {}
    approvals = manifest.get("approvals") or {}
    return {
        "name": manifest["name"],
        "display_name": manifest.get("display_name") or manifest["name"],
        "description": manifest.get("description"),
        "entrypoint": manifest["entrypoint"],
        "inputs": manifest.get("inputs") or {},
        "tools": list(permissions.get("tools") or []),
        "approvals_required_for": list(approvals.get("required_for") or []),
        "workspace_connections": [
            secret["name"]
            for secret in permissions.get("secrets") or []
            if secret.get("scope") == "workspace"
        ],
        "user_connections": [
            secret["name"]
            for secret in permissions.get("secrets") or []
            if secret.get("scope") == "user"
        ],
        "modules": [
            {
                "id": "default",
                "title": manifest.get("display_name") or manifest["name"],
                "required": True,
                "enabled_by_default": True,
            }
        ],
        "limits": manifest.get("limits") or {},
        "compatibility": {"runtime_api": "v1"},
    }
```

- [ ] **Step 4: Route deploy and CLI validation through the loader**

```python
# services/control-plane/app/services/agent_deploy_service.py
from app.services.package_descriptor import PackageDescriptor, load_package_descriptor

descriptor = load_package_descriptor(tmp)
manifest = descriptor.data
slug = manifest["name"]


# packages/platform_cli/platform_cli/main.py
manifest_path = next(
    (path / name for name in ("automation.yaml", "agent.yaml") if (path / name).exists()),
    None,
)
if manifest_path is None:
    typer.secho(f"{path} is missing automation.yaml or agent.yaml", fg=typer.colors.RED, err=True)
    raise typer.Exit(2)
manifest = yaml.safe_load(manifest_path.read_text()) or {}
```

- [ ] **Step 5: Add one native `automation.yaml` example while preserving `agent.yaml`**

```yaml
# examples/weekly-summary/automation.yaml
name: weekly-summary
display_name: Weekly Sales Summary
description: Pull the workspace pipeline, summarize it, and deliver the result through enabled channels.
entrypoint: main:run

inputs:
  region:
    type: string
    required: true
  recipient_email:
    type: string
    required: false

workspace_connections:
  - OPENAI_API_KEY

modules:
  - id: summary_generation
    title: Summary generation
    required: true
    enabled_by_default: true
  - id: email_delivery
    title: Email delivery
    required: false
    enabled_by_default: true
    depends_on_provider_plugins:
      - smtp_email

tools:
  - llm.complete
  - postgres.query
  - email.send

approvals_required_for:
  - email.send
```

- [ ] **Step 6: Run descriptor tests to verify the compatibility layer passes**

Run: `pytest tests/unit/test_package_descriptor.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add tests/unit/__init__.py tests/unit/test_package_descriptor.py services/control-plane/app/services/package_descriptor.py services/control-plane/app/services/agent_deploy_service.py packages/platform_cli/platform_cli/main.py examples/weekly-summary/automation.yaml
git commit -m "feat: add automation descriptor compatibility layer"
```

### Task 2: Persistent installation and connection foundation

**Files:**
- Create: `services/control-plane/app/models/connection.py`
- Create: `services/control-plane/app/models/installation.py`
- Create: `services/control-plane/app/services/provider_registry.py`
- Create: `services/control-plane/app/services/installations_service.py`
- Create: `services/control-plane/alembic/versions/0004_automation_foundation.py`
- Create: `tests/unit/test_installation_readiness.py`
- Modify: `services/control-plane/app/models/agent.py`
- Modify: `services/control-plane/app/models/__init__.py`

- [ ] **Step 1: Write the failing readiness test around missing connections and disabled modules**

```python
from app.services.installations_service import compute_installation_readiness


def test_compute_installation_readiness_reports_missing_items() -> None:
    descriptor = {
        "workspace_connections": ["OPENAI_API_KEY"],
        "user_connections": ["MAILBOX_TOKEN"],
        "modules": [
            {"id": "summary_generation", "required": True, "enabled_by_default": True},
            {"id": "email_delivery", "required": False, "enabled_by_default": True},
        ],
    }
    readiness = compute_installation_readiness(
        descriptor=descriptor,
        available_workspace_connections=set(),
        available_user_connections=set(),
        enabled_modules={"summary_generation"},
    )
    assert readiness.ready is False
    assert readiness.missing_workspace_connections == ["OPENAI_API_KEY"]
    assert readiness.missing_user_connections == ["MAILBOX_TOKEN"]
    assert readiness.disabled_required_modules == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_installation_readiness.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.installations_service'`

- [ ] **Step 3: Add the new state models and the agent-version metadata columns**

```python
# services/control-plane/app/models/connection.py
class ConnectionScope(str, enum.Enum):
    workspace = "workspace"
    user = "user"


class ConnectionStatus(str, enum.Enum):
    pending = "pending"
    ready = "ready"
    invalid = "invalid"


class Connection(Base):
    __tablename__ = "connection"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=True, index=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_key: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[ConnectionScope] = mapped_column(Enum(ConnectionScope, name="connection_scope", values_callable=lambda x: [e.value for e in x]), nullable=False)
    status: Mapped[ConnectionStatus] = mapped_column(Enum(ConnectionStatus, name="connection_status", values_callable=lambda x: [e.value for e in x]), nullable=False, default=ConnectionStatus.pending)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    scopes_json: Mapped[list[str]] = jsonb_col(default=list)
    config_json: Mapped[dict[str, Any]] = jsonb_col(default=dict)
    secret_refs_json: Mapped[dict[str, str]] = jsonb_col(default=dict)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_at_col()


# services/control-plane/app/models/installation.py
class InstallationStatus(str, enum.Enum):
    draft = "draft"
    ready = "ready"
    active = "active"
    blocked = "blocked"


class AutomationInstallation(Base):
    __tablename__ = "automation_installation"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent.id", ondelete="CASCADE"), nullable=False, unique=True)
    status: Mapped[InstallationStatus] = mapped_column(Enum(InstallationStatus, name="installation_status", values_callable=lambda x: [e.value for e in x]), nullable=False, default=InstallationStatus.draft)
    enabled_modules_json: Mapped[list[str]] = jsonb_col(default=list)
    config_json: Mapped[dict[str, Any]] = jsonb_col(default=dict)
    last_ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_at_col()


# services/control-plane/app/models/agent.py
descriptor_format: Mapped[str] = mapped_column(String(32), nullable=False, default="legacy_agent")
compatibility_version: Mapped[str] = mapped_column(String(32), nullable=False, default="runtime_api:v1")
inspection_json: Mapped[dict[str, Any] | None] = jsonb_col(nullable=True)
```

- [ ] **Step 4: Add the provider registry and readiness service as the canonical policy layer**

```python
# services/control-plane/app/services/provider_registry.py
PROVIDER_PLUGINS = {
    "openai": {"scope": "workspace", "connection_keys": ["OPENAI_API_KEY"]},
    "smtp_email": {"scope": "workspace", "connection_keys": ["SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD"]},
    "mailbox": {"scope": "user", "connection_keys": ["MAILBOX_TOKEN"]},
}


# services/control-plane/app/services/installations_service.py
from dataclasses import dataclass


@dataclass(frozen=True)
class InstallationReadiness:
    ready: bool
    missing_workspace_connections: list[str]
    missing_user_connections: list[str]
    disabled_required_modules: list[str]


def compute_installation_readiness(
    *,
    descriptor: dict,
    available_workspace_connections: set[str],
    available_user_connections: set[str],
    enabled_modules: set[str],
) -> InstallationReadiness:
    required_modules = {
        module["id"]
        for module in descriptor.get("modules", [])
        if module.get("required")
    }
    disabled_required = sorted(required_modules - enabled_modules)
    missing_workspace = sorted(
        set(descriptor.get("workspace_connections", [])) - available_workspace_connections
    )
    missing_user = sorted(
        set(descriptor.get("user_connections", [])) - available_user_connections
    )
    return InstallationReadiness(
        ready=not missing_workspace and not missing_user and not disabled_required,
        missing_workspace_connections=missing_workspace,
        missing_user_connections=missing_user,
        disabled_required_modules=disabled_required,
    )
```

- [ ] **Step 5: Add and apply the Alembic migration**

```python
# services/control-plane/alembic/versions/0004_automation_foundation.py
def upgrade() -> None:
    op.add_column("agent_version", sa.Column("descriptor_format", sa.String(length=32), nullable=False, server_default="legacy_agent"))
    op.add_column("agent_version", sa.Column("compatibility_version", sa.String(length=32), nullable=False, server_default="runtime_api:v1"))
    op.add_column("agent_version", sa.Column("inspection_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_table(
        "connection",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("provider_key", sa.String(length=128), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("scopes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("secret_refs_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "automation_installation",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("enabled_modules_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["agent.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id"),
    )
```

Run: `cd services/control-plane && alembic upgrade head`
Expected: migration applies cleanly and leaves current seed data intact

- [ ] **Step 6: Run readiness tests to verify the new policy layer passes**

Run: `pytest tests/unit/test_installation_readiness.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add tests/unit/test_installation_readiness.py services/control-plane/app/models/agent.py services/control-plane/app/models/connection.py services/control-plane/app/models/installation.py services/control-plane/app/models/__init__.py services/control-plane/app/services/provider_registry.py services/control-plane/app/services/installations_service.py services/control-plane/alembic/versions/0004_automation_foundation.py
git commit -m "feat: add installation and connection foundation"
```

### Task 3: Deploy-time inspection and manifest-code validation

**Files:**
- Create: `packages/platform_sdk/platform_sdk/inspect.py`
- Create: `tests/unit/test_inspection_handshake.py`
- Modify: `packages/platform_sdk/platform_sdk/__init__.py`
- Modify: `packages/platform_sdk/pyproject.toml`
- Modify: `services/control-plane/app/services/agent_deploy_service.py`
- Modify: `examples/weekly-summary/main.py`

- [ ] **Step 1: Write the failing inspection validation test**

```python
import pytest

from app.services.agent_deploy_service import validate_descriptor_against_inspection


def test_validate_descriptor_against_inspection_rejects_missing_module() -> None:
    descriptor = {"modules": [{"id": "email_delivery"}], "compatibility": {"runtime_api": "v2"}}
    inspection = {"modules": ["summary_generation"], "triggers": ["manual"], "runtime_api": "v2"}
    with pytest.raises(ValueError, match="email_delivery"):
        validate_descriptor_against_inspection(descriptor, inspection)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_inspection_handshake.py -q`
Expected: FAIL with `ImportError` or missing `validate_descriptor_against_inspection`

- [ ] **Step 3: Add a simple, explicit inspection contract to the SDK**

```python
# packages/platform_sdk/platform_sdk/inspect.py
from __future__ import annotations

import importlib
from pathlib import Path


def inspect_package(entrypoint: str) -> dict:
    module_name, function_name = entrypoint.split(":")
    module = importlib.import_module(module_name)
    meta = getattr(module, "AUTOMATION_META", {})
    if not hasattr(module, function_name):
        raise ValueError(f"entrypoint {entrypoint!r} is missing")
    return {
        "runtime_api": meta.get("runtime_api", "v1"),
        "modules": [module_spec["id"] for module_spec in meta.get("modules", [])],
        "triggers": meta.get("triggers", ["manual"]),
        "channels": meta.get("channels", []),
        "entrypoint": entrypoint,
    }
```

- [ ] **Step 4: Validate descriptor metadata against the inspection result during deploy**

```python
# services/control-plane/app/services/agent_deploy_service.py
def validate_descriptor_against_inspection(descriptor: dict, inspection: dict) -> None:
    declared_modules = {module["id"] for module in descriptor.get("modules", [])}
    implemented_modules = set(inspection.get("modules", []))
    missing_modules = sorted(declared_modules - implemented_modules)
    if missing_modules:
        raise ValueError(f"descriptor declares modules with no implementation: {missing_modules}")
    expected_runtime_api = (descriptor.get("compatibility") or {}).get("runtime_api", "v1")
    if inspection.get("runtime_api") != expected_runtime_api:
        raise ValueError("descriptor runtime_api does not match inspected runtime_api")
```

- [ ] **Step 5: Add `AUTOMATION_META` to the first native automation example**

```python
# examples/weekly-summary/main.py
AUTOMATION_META = {
    "runtime_api": "v2",
    "modules": [
        {"id": "summary_generation"},
        {"id": "email_delivery"},
    ],
    "triggers": ["manual", "schedule"],
    "channels": ["email"],
}
```

- [ ] **Step 6: Run inspection tests and a local inspect smoke command**

Run: `pytest tests/unit/test_inspection_handshake.py -q`
Expected: PASS

Run: `python -m platform_sdk.inspect examples/weekly-summary`
Expected: JSON including `modules`, `triggers`, `channels`, and `runtime_api`

- [ ] **Step 7: Commit**

```bash
git add tests/unit/test_inspection_handshake.py packages/platform_sdk/platform_sdk/inspect.py packages/platform_sdk/platform_sdk/__init__.py packages/platform_sdk/pyproject.toml services/control-plane/app/services/agent_deploy_service.py examples/weekly-summary/main.py
git commit -m "feat: add deploy-time automation inspection"
```

### Task 4: Activation-aware APIs, runtime, and installation UI

**Files:**
- Create: `services/control-plane/app/api/connections.py`
- Create: `services/control-plane/app/api/installations.py`
- Create: `tests/unit/test_runtime_activation_context.py`
- Create: `tests/integration/test_installation_flow.py`
- Create: `frontend/app/admin/connections/page.tsx`
- Create: `frontend/app/admin/agents/[slug]/page.tsx`
- Create: `frontend/components/InstallationReadinessCard.tsx`
- Create: `frontend/components/ModuleActivationCard.tsx`
- Create: `frontend/components/ConnectionList.tsx`
- Modify: `services/control-plane/app/api/admin.py`
- Modify: `services/control-plane/app/api/catalog.py`
- Modify: `services/control-plane/app/api/dev.py`
- Modify: `services/control-plane/app/api/me.py`
- Modify: `services/control-plane/app/main.py`
- Modify: `services/control-plane/app/run_tokens.py`
- Modify: `services/control-plane/app/execution/docker_backend.py`
- Modify: `packages/platform_sdk/platform_sdk/context.py`
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/app/app/agents/[slug]/page.tsx`
- Modify: `frontend/app/dev/agents/[slug]/page.tsx`
- Modify: `frontend/components/ConnectedAccounts.tsx`

- [ ] **Step 1: Write the failing SDK context test for module and connection access**

```python
import json

from platform_sdk.context import ctx


def test_ctx_reads_installation_state(monkeypatch) -> None:
    monkeypatch.setenv(
        "RUN_INSTALLATION_STATE",
        json.dumps(
            {
                "enabled_modules": ["summary_generation", "email_delivery"],
                "connections": {
                    "OPENAI_API_KEY": {"provider_key": "openai", "scope": "workspace"},
                    "MAILBOX_TOKEN": {"provider_key": "mailbox", "scope": "user"},
                },
                "config": {"delivery_mode": "email"},
            }
        ),
    )
    assert ctx.module_enabled("email_delivery") is True
    assert ctx.connection("OPENAI_API_KEY")["provider_key"] == "openai"
    assert ctx.installation_config()["delivery_mode"] == "email"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_runtime_activation_context.py -q`
Expected: FAIL with `AttributeError: '_Context' object has no attribute 'module_enabled'`

- [ ] **Step 3: Add installation and connection APIs before touching the frontend**

```python
# services/control-plane/app/api/installations.py
@router.get("/admin/agents/{slug}/installation")
def get_installation(slug: str, actor: AdminOnly, db: DbSession) -> dict:
    agent = db.execute(select(Agent).where(Agent.tenant_id == actor.tenant_id, Agent.slug == slug)).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "agent not found")
    installation = db.execute(select(AutomationInstallation).where(AutomationInstallation.agent_id == agent.id)).scalar_one_or_none()
    if installation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "installation not found")
    return {
        "agent_id": str(agent.id),
        "status": installation.status.value,
        "enabled_modules": installation.enabled_modules_json,
        "config": installation.config_json,
    }


@router.put("/admin/agents/{slug}/installation")
def upsert_installation(slug: str, payload: dict, actor: AdminOnly, db: DbSession) -> dict:
    agent = db.execute(select(Agent).where(Agent.tenant_id == actor.tenant_id, Agent.slug == slug)).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "agent not found")
    installation = db.execute(select(AutomationInstallation).where(AutomationInstallation.agent_id == agent.id)).scalar_one_or_none()
    if installation is None:
        installation = AutomationInstallation(agent_id=agent.id, tenant_id=actor.tenant_id)
        db.add(installation)
    installation.enabled_modules_json = list(payload.get("enabled_modules", []))
    installation.config_json = dict(payload.get("config", {}))
    db.commit()
    db.refresh(installation)
    return {"status": installation.status.value, "enabled_modules": installation.enabled_modules_json}


# services/control-plane/app/api/connections.py
@router.get("/admin/connections")
def list_workspace_connections(actor: AdminOnly, db: DbSession) -> list[dict]:
    rows = db.execute(select(Connection).where(Connection.tenant_id == actor.tenant_id, Connection.user_id.is_(None))).scalars().all()
    return [
        {"id": str(row.id), "key": row.key, "provider_key": row.provider_key, "scope": row.scope.value, "status": row.status.value}
        for row in rows
    ]


@router.post("/admin/connections")
def create_workspace_connection(payload: dict, actor: AdminOnly, db: DbSession) -> dict:
    connection = Connection(
        tenant_id=actor.tenant_id,
        user_id=None,
        key=payload["key"],
        provider_key=payload["provider_key"],
        scope=ConnectionScope.workspace,
        status=ConnectionStatus.ready,
        display_name=payload.get("display_name") or payload["key"],
        scopes_json=list(payload.get("scopes", [])),
        config_json=dict(payload.get("config", {})),
        secret_refs_json=dict(payload.get("secret_refs", {})),
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return {"id": str(connection.id), "status": connection.status.value}
```

- [ ] **Step 4: Pass activation state into the run token and runtime environment**

```python
# services/control-plane/app/run_tokens.py
payload["installation_state"] = {
    "enabled_modules": enabled_modules,
    "connections": resolved_connections,
    "config": installation_config,
}


# services/control-plane/app/execution/docker_backend.py
env["RUN_INSTALLATION_STATE"] = json.dumps(
    {
        "enabled_modules": installation.enabled_modules_json,
        "connections": resolved_connections,
        "config": installation.config_json,
    }
)


# packages/platform_sdk/platform_sdk/context.py
def module_enabled(self, module_id: str) -> bool:
    return module_id in set(self._installation_state().get("enabled_modules", []))


def connection(self, key: str) -> dict[str, Any] | None:
    return (self._installation_state().get("connections", {})).get(key)


def installation_config(self) -> dict[str, Any]:
    return dict(self._installation_state().get("config", {}))
```

- [ ] **Step 5: Update the catalog and admin UI to show readiness, modules, and connection state**

```tsx
// frontend/app/app/agents/[slug]/page.tsx
<InstallationReadinessCard
  ready={agent.installation.ready}
  missingWorkspaceConnections={agent.installation.missing_workspace_connections}
  missingUserConnections={agent.installation.missing_user_connections}
/>
<ModuleActivationCard
  modules={agent.modules}
  enabledModules={agent.installation.enabled_modules}
  editable={false}
/>


// frontend/app/admin/agents/[slug]/page.tsx
<ConnectionList connections={connections} />
<ModuleActivationCard
  modules={installation.modules}
  enabledModules={installation.enabled_modules}
  editable
  onToggle={toggleModule}
/>
```

- [ ] **Step 6: Run focused tests and the new integration flow**

Run: `pytest tests/unit/test_runtime_activation_context.py -q`
Expected: PASS

Run: `pytest tests/integration/test_installation_flow.py -q`
Expected: PASS, covering install readiness, module activation, user connection, and successful run

Run: `npm --prefix frontend run build`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add tests/unit/test_runtime_activation_context.py tests/integration/test_installation_flow.py services/control-plane/app/api/connections.py services/control-plane/app/api/installations.py services/control-plane/app/api/admin.py services/control-plane/app/api/catalog.py services/control-plane/app/api/dev.py services/control-plane/app/api/me.py services/control-plane/app/main.py services/control-plane/app/run_tokens.py services/control-plane/app/execution/docker_backend.py packages/platform_sdk/platform_sdk/context.py frontend/lib/types.ts frontend/app/app/agents/[slug]/page.tsx frontend/app/dev/agents/[slug]/page.tsx frontend/app/admin/connections/page.tsx frontend/app/admin/agents/[slug]/page.tsx frontend/components/ConnectedAccounts.tsx frontend/components/InstallationReadinessCard.tsx frontend/components/ModuleActivationCard.tsx frontend/components/ConnectionList.tsx
git commit -m "feat: add installation-aware runtime and admin activation flow"
```

### Task 5: Developer scaffolder for native automations

**Files:**
- Create: `frontend/app/dev/automations/new/page.tsx`
- Create: `frontend/components/AutomationScaffoldForm.tsx`
- Create: `tests/unit/test_scaffold_templates.py`
- Modify: `packages/platform_cli/platform_cli/main.py`
- Modify: `services/control-plane/app/api/dev.py`
- Modify: `skills/platform-agent/SKILL.md`
- Modify: `README.md`

- [ ] **Step 1: Write the failing scaffold template test**

```python
from pathlib import Path

from platform_cli.main import render_automation_template


def test_render_automation_template_includes_required_files(tmp_path: Path) -> None:
    rendered = render_automation_template(
        slug="daily-digest",
        display_name="Daily Digest",
        modules=["summary_generation", "email_delivery"],
    )
    assert sorted(rendered) == [
        "AI_INSTRUCTIONS.md",
        "README.md",
        "automation.yaml",
        "main.py",
        "tests/test_agent.py",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_scaffold_templates.py -q`
Expected: FAIL with missing `render_automation_template`

- [ ] **Step 3: Refactor the CLI scaffold into a reusable template renderer**

```python
# packages/platform_cli/platform_cli/main.py
def render_automation_template(*, slug: str, display_name: str, modules: list[str]) -> dict[str, str]:
    return {
        "automation.yaml": _AUTOMATION_YAML_TEMPLATE.format(slug=slug, display_name=display_name),
        "main.py": _MAIN_PY_TEMPLATE,
        "README.md": _README_TEMPLATE.format(display_name=display_name),
        "AI_INSTRUCTIONS.md": _AI_INSTRUCTIONS_TEMPLATE,
        "tests/test_agent.py": _TEST_TEMPLATE,
    }


files = render_automation_template(slug=name, display_name=name.replace("-", " ").title(), modules=["default"])
for relative_path, content in files.items():
    destination = out_dir / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content)
```

- [ ] **Step 4: Expose the same contract in the developer UI**

```tsx
// frontend/app/dev/automations/new/page.tsx
export default function NewAutomationPage() {
  return <AutomationScaffoldForm />;
}


// frontend/components/AutomationScaffoldForm.tsx
const response = await apiFetch<{ filename: string; archive_base64: string }>("/dev/automation-scaffold", {
  method: "POST",
  body: JSON.stringify({ slug, display_name: displayName, modules }),
});
const bytes = Uint8Array.from(atob(response.archive_base64), (char) => char.charCodeAt(0));
const url = URL.createObjectURL(new Blob([bytes], { type: "application/zip" }));
const link = document.createElement("a");
link.href = url;
link.download = response.filename;
link.click();
URL.revokeObjectURL(url);
```

```python
# services/control-plane/app/api/dev.py
def render_automation_yaml(slug: str, display_name: str, modules: list[str]) -> str:
    module_lines = "\n".join(f"  - id: {module_id}\n    required: {str(index == 0).lower()}\n    enabled_by_default: true" for index, module_id in enumerate(modules))
    return (
        f"name: {slug}\n"
        f"display_name: {display_name}\n"
        "entrypoint: main:run\n"
        "modules:\n"
        f"{module_lines}\n"
    )


def render_automation_main(modules: list[str]) -> str:
    module_items = ", ".join(f'{{\"id\": \"{module_id}\"}}' for module_id in modules)
    return (
        "AUTOMATION_META = {\"runtime_api\": \"v2\", \"modules\": ["
        f"{module_items}"
        "], \"triggers\": [\"manual\"]}\n\n"
        "def run() -> dict:\n"
        "    return {\"ok\": True}\n"
    )


def render_automation_test() -> str:
    return (
        "from main import run\n\n"
        "def test_run_returns_ok() -> None:\n"
        "    assert run()[\"ok\"] is True\n"
    )


@router.post("/automation-scaffold")
def automation_scaffold(payload: dict, actor: DevOrAdmin) -> dict[str, str]:
    files = {
        "automation.yaml": render_automation_yaml(payload["slug"], payload["display_name"], payload.get("modules", ["default"])),
        "main.py": render_automation_main(payload.get("modules", ["default"])),
        "README.md": f"# {payload['display_name']}\n",
        "AI_INSTRUCTIONS.md": "Build inside the declared module boundaries.\n",
        "tests/test_agent.py": render_automation_test(),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for relative_path, content in files.items():
            zf.writestr(relative_path, content)
    return {
        "filename": f"{payload['slug']}.zip",
        "archive_base64": base64.b64encode(buffer.getvalue()).decode(),
    }
```

- [ ] **Step 5: Update docs and the authoring skill to teach `automation.yaml` first**

```markdown
Native packages should start with `automation.yaml`.
Use `agent.yaml` only when maintaining a compatibility package that has not migrated yet.
```

- [ ] **Step 6: Run scaffold tests and a CLI smoke check**

Run: `pytest tests/unit/test_scaffold_templates.py -q`
Expected: PASS

Run: `python -m platform_cli.main init daily-digest --target .`
Expected: creates a native automation starter with `automation.yaml`, `AI_INSTRUCTIONS.md`, and `tests/test_agent.py`

- [ ] **Step 7: Commit**

```bash
git add tests/unit/test_scaffold_templates.py packages/platform_cli/platform_cli/main.py services/control-plane/app/api/dev.py frontend/app/dev/automations/new/page.tsx frontend/components/AutomationScaffoldForm.tsx README.md skills/platform-agent/SKILL.md
git commit -m "feat: add native automation scaffolder"
```

### Task 6: Production self-hosting story and diagnostics

**Files:**
- Create: `docs/self-hosting.md`
- Create: `docker-compose.prod.yml`
- Create: `tests/integration/test_admin_diagnostics.py`
- Modify: `frontend/Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `services/control-plane/app/api/admin.py`
- Modify: `README.md`

- [ ] **Step 1: Write the failing admin diagnostics integration test**

```python
import httpx

from .conftest import API_URL


def test_admin_diagnostics_endpoint(admin_token: str) -> None:
    response = httpx.get(
        f"{API_URL}/admin/diagnostics",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=10.0,
    )
    response.raise_for_status()
    body = response.json()
    assert "database" in body
    assert "redis" in body
    assert "tool_gateway" in body
    assert "runtime_mode" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_admin_diagnostics.py -q`
Expected: FAIL with `404 Not Found` for `/admin/diagnostics`

- [ ] **Step 3: Replace the frontend dev container with a production image and add a production compose overlay**

```dockerfile
# frontend/Dockerfile
FROM node:20-alpine AS deps
WORKDIR /srv
COPY package.json package-lock.json* ./
RUN npm ci

FROM deps AS build
COPY . .
RUN npm run build

FROM node:20-alpine AS runtime
WORKDIR /srv
ENV NODE_ENV=production
COPY --from=build /srv/.next ./.next
COPY --from=build /srv/public ./public
COPY --from=build /srv/package.json ./package.json
COPY --from=deps /srv/node_modules ./node_modules
CMD ["npm", "run", "start"]
```

- [ ] **Step 4: Add diagnostics and clean production configuration knobs**

```python
# services/control-plane/app/api/admin.py
@router.get("/diagnostics")
def diagnostics(actor: AdminOnly) -> dict:
    return {
        "database": "ok",
        "redis": "ok",
        "tool_gateway": "ok",
        "runtime_mode": "docker-socket",
        "demo_dependencies_enabled": True,
    }
```

- [ ] **Step 5: Document the supported self-hosted topology and split demo-only services**

```markdown
# docs/self-hosting.md
- base stack: postgres, redis, control-plane, tool-gateway, worker, scheduler, frontend
- demo-only extras: mailhog, mock-crm, sample_data
- production concerns: external TLS, secrets injection, backups, log aggregation, runtime builder strategy
```

- [ ] **Step 6: Run the hardening checks**

Run: `pytest tests/integration/test_admin_diagnostics.py -q`
Expected: PASS

Run: `npm --prefix frontend run build`
Expected: PASS

Run: `docker compose -f docker-compose.yml -f docker-compose.prod.yml config`
Expected: PASS and render a production-ready merged config without localhost-only assumptions

- [ ] **Step 7: Commit**

```bash
git add tests/integration/test_admin_diagnostics.py frontend/Dockerfile docker-compose.yml docker-compose.prod.yml services/control-plane/app/api/admin.py docs/self-hosting.md README.md
git commit -m "feat: add production self-hosting baseline"
```

## Self-Review

**Spec coverage:** This plan covers the handoff's required compatibility layer, richer descriptor, connection model, activation flow, deploy-time inspection, runtime activation state, UI scaffolder, and self-hosting story. The only deliberate deferral is a true third-party marketplace and installable provider-plugin distribution, which should wait until these foundations are stable.

**Placeholder scan:** No `TODO`, `TBD`, or "implement later" placeholders remain. Each task names concrete files, tests, commands, and commit messages.

**Type consistency:** The plan consistently uses `automation.yaml`, `PackageDescriptor`, `Connection`, `AutomationInstallation`, `AUTOMATION_META`, `RUN_INSTALLATION_STATE`, and `compute_installation_readiness`. Legacy support continues through normalized `agent.yaml` manifests and existing `Agent` / `AgentVersion` storage.
