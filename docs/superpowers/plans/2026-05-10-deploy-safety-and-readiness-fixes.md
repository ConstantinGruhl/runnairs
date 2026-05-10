# Deploy Safety And Readiness Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the deploy-time safety hole, make connection readiness depend on real stored credentials, and block unready automations before they can be enqueued or executed.

**Architecture:** Keep the current automation foundation, but move inspection out of the control-plane Python process and into a tightly sandboxed transient container built from the agent image. Treat `Connection` rows as metadata plus health state, while `Secret` rows remain the credential source of truth; readiness becomes the intersection of declared requirements, enabled modules, and actual secret-backed connection availability. Use one shared readiness-enforcement helper from manual runs, scheduled runs, and execution-time defense-in-depth so every entry path agrees.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Docker SDK for Python, platform SDK CLI inspection entrypoint, pytest, httpx

---

## Scope Check

These four findings are tightly coupled and should stay in one plan:

- Findings 1 and 2 are the same deploy-time inspection subsystem.
- Finding 3 changes the truth source for connection availability.
- Finding 4 depends on that corrected truth source to gate runs correctly.

Splitting this into multiple plans would create temporary states where the platform still reports incorrect readiness or still executes uploaded code in the control-plane process.

## File Structure

**Create:**
- `services/control-plane/app/services/package_inspection.py`
- `tests/unit/test_package_inspection.py`
- `tests/unit/test_run_readiness.py`
- `tests/integration/test_connection_sync.py`

**Modify:**
- `services/control-plane/app/services/agent_deploy_service.py`
- `services/control-plane/app/services/installations_service.py`
- `services/control-plane/app/api/connections.py`
- `services/control-plane/app/api/secrets.py`
- `services/control-plane/app/api/me.py`
- `services/control-plane/app/api/runs.py`
- `services/control-plane/app/scheduler.py`
- `services/control-plane/app/execution/docker_backend.py`
- `packages/platform_sdk/platform_sdk/inspect.py`
- `tests/unit/test_inspection_handshake.py`
- `tests/integration/test_installation_flow.py`

### Task 1: Safe Containerized Deploy Inspection

**Files:**
- Create: `services/control-plane/app/services/package_inspection.py`
- Create: `tests/unit/test_package_inspection.py`
- Modify: `services/control-plane/app/services/agent_deploy_service.py`
- Modify: `packages/platform_sdk/platform_sdk/inspect.py`
- Test: `tests/unit/test_package_inspection.py`

- [ ] **Step 1: Write the failing unit tests for sandboxed image inspection**

```python
import json

import pytest

from app.services.package_inspection import InspectionError, inspect_image_package


class FakeContainer:
    def __init__(self, *, exit_code: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.started = False
        self.removed = False
        self.wait_timeout = None

    def start(self) -> None:
        self.started = True

    def wait(self, timeout: int) -> dict[str, int]:
        self.wait_timeout = timeout
        return {"StatusCode": self.exit_code}

    def logs(self, *, stdout: bool = True, stderr: bool = False) -> bytes:
        if stdout and not stderr:
            return self.stdout.encode("utf-8")
        if stderr and not stdout:
            return self.stderr.encode("utf-8")
        raise AssertionError("unexpected log stream request")

    def remove(self, *, force: bool = False) -> None:
        self.removed = force


class FakeContainers:
    def __init__(self, container: FakeContainer) -> None:
        self.container = container
        self.created_kwargs = None

    def create(self, **kwargs):
        self.created_kwargs = kwargs
        return self.container


class FakeClient:
    def __init__(self, container: FakeContainer) -> None:
        self.containers = FakeContainers(container)


def test_inspect_image_package_uses_locked_down_container(monkeypatch) -> None:
    payload = {
        "runtime_api": "v2",
        "modules": ["summary_generation", "email_delivery"],
        "triggers": ["manual"],
        "channels": ["email"],
        "entrypoint": "main:run",
    }
    container = FakeContainer(stdout=json.dumps(payload))
    client = FakeClient(container)
    monkeypatch.setattr("app.services.package_inspection.docker.from_env", lambda: client)

    result = inspect_image_package(image_tag="agent-123:v1", entrypoint="main:run")

    assert result == payload
    assert container.started is True
    assert container.removed is True
    assert client.containers.created_kwargs["image"] == "agent-123:v1"
    assert client.containers.created_kwargs["network_disabled"] is True
    assert client.containers.created_kwargs["read_only"] is True
    assert client.containers.created_kwargs["cap_drop"] == ["ALL"]
    assert client.containers.created_kwargs["entrypoint"] == [
        "python",
        "-m",
        "platform_sdk.inspect",
        "/agent",
        "main:run",
    ]


def test_inspect_image_package_raises_on_non_zero_exit(monkeypatch) -> None:
    container = FakeContainer(exit_code=2, stderr="entrypoint 'main:run' is missing")
    client = FakeClient(container)
    monkeypatch.setattr("app.services.package_inspection.docker.from_env", lambda: client)

    with pytest.raises(InspectionError, match="entrypoint 'main:run' is missing"):
        inspect_image_package(image_tag="agent-123:v1", entrypoint="main:run")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_package_inspection.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.package_inspection'`

- [ ] **Step 3: Implement the sandboxed image inspection helper**

```python
# services/control-plane/app/services/package_inspection.py
from __future__ import annotations

import json
from typing import Any

import docker
from docker.errors import APIError, DockerException, ImageNotFound


INSPECTION_TIMEOUT_SECONDS = 15


class InspectionError(Exception):
    """Raised when inspection cannot complete safely or returns invalid data."""


def inspect_image_package(*, image_tag: str, entrypoint: str) -> dict[str, Any]:
    try:
        client = docker.from_env()
    except DockerException as e:
        raise InspectionError(f"cannot reach docker daemon for inspection: {e}") from e

    container = None
    try:
        container = client.containers.create(
            image=image_tag,
            entrypoint=["python", "-m", "platform_sdk.inspect", "/agent", entrypoint],
            network_disabled=True,
            read_only=True,
            tmpfs={"/tmp": "rw,size=16m"},
            mem_limit="128m",
            nano_cpus=int(0.5e9),
            cap_drop=["ALL"],
            security_opt=["no-new-privileges"],
            working_dir="/agent",
            environment={},
            detach=True,
            labels={
                "platform.kind": "agent-inspection",
                "platform.image_tag": image_tag,
            },
        )
        container.start()
        result = container.wait(timeout=INSPECTION_TIMEOUT_SECONDS)
        exit_code = int(result.get("StatusCode", -1))
        stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace").strip()
        stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace").strip()

        if exit_code != 0:
            raise InspectionError(stderr or f"inspection container exited with code {exit_code}")

        payload = json.loads(stdout)
        if not isinstance(payload, dict):
            raise InspectionError("inspection output must be a JSON object")
        return payload
    except ImageNotFound as e:
        raise InspectionError(f"inspection image {image_tag!r} not found") from e
    except APIError as e:
        raise InspectionError(f"docker API error during inspection: {e}") from e
    except json.JSONDecodeError as e:
        raise InspectionError(f"inspection returned invalid JSON: {e}") from e
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass
```

- [ ] **Step 4: Replace in-process imports with containerized inspection after image build**

```python
# services/control-plane/app/services/agent_deploy_service.py
from app.services.package_inspection import InspectionError, inspect_image_package


def deploy(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
    archive_bytes: bytes,
) -> DeployedAgent:
    with tempfile.TemporaryDirectory(prefix="agent-deploy-") as tmpdir:
        tmp = Path(tmpdir)
        _safe_extract(archive_bytes, tmp)

        if not (tmp / "main.py").exists():
            raise DeployError("archive is missing main.py at the top level")

        try:
            descriptor = load_package_descriptor(tmp)
        except ValueError as e:
            raise DeployError(str(e)) from e

        manifest = descriptor.data
        slug = manifest["name"]

        agent = _upsert_agent(db, tenant_id=tenant_id, slug=slug, manifest=manifest, created_by=created_by)
        version = _next_version(db, agent.id)
        image_tag = f"agent-{agent.id}:{version}"

        _write_dockerfile(tmp)
        _build_image(tmp, image_tag)

        try:
            inspection = inspect_image_package(image_tag=image_tag, entrypoint=manifest["entrypoint"])
            validate_descriptor_against_inspection(manifest, inspection)
        except (InspectionError, ValueError) as e:
            _remove_image_if_present(image_tag)
            raise DeployError(str(e)) from e

        version_row = AgentVersion(
            agent_id=agent.id,
            version=version,
            manifest_json=manifest,
            descriptor_format=descriptor.format,
            compatibility_version=_compatibility_version(manifest),
            inspection_json=inspection,
            image_tag=image_tag,
            created_by=created_by,
        )
        db.add(version_row)
        db.flush()

    db.commit()
    return DeployedAgent(
        agent_id=agent.id,
        slug=agent.slug,
        version=version,
        image_tag=image_tag,
        status=agent.status.value,
    )


def _remove_image_if_present(tag: str) -> None:
    try:
        docker.from_env().images.remove(tag, force=True)
    except Exception:
        logger.warning("failed to remove inspection image %s after deploy validation failure", tag)
```

- [ ] **Step 5: Make the SDK inspection CLI return clean stderr on failure**

```python
# packages/platform_sdk/platform_sdk/inspect.py
def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: python -m platform_sdk.inspect <path> [entrypoint]", file=sys.stderr)
        return 2

    path = Path(args[0])
    entrypoint = args[1] if len(args) > 1 else None
    try:
        payload = inspect_package(path, entrypoint=entrypoint)
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 2

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Run the inspection tests to verify the safe path works**

Run: `pytest tests/unit/test_package_inspection.py tests/unit/test_inspection_handshake.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add services/control-plane/app/services/package_inspection.py services/control-plane/app/services/agent_deploy_service.py packages/platform_sdk/platform_sdk/inspect.py tests/unit/test_package_inspection.py tests/unit/test_inspection_handshake.py
git commit -m "fix: run deploy inspection inside sandboxed containers"
```

### Task 2: Make Connection Readiness Depend On Real Stored Credentials

**Files:**
- Create: `tests/integration/test_connection_sync.py`
- Modify: `services/control-plane/app/services/installations_service.py`
- Modify: `services/control-plane/app/api/connections.py`
- Modify: `services/control-plane/app/api/secrets.py`
- Modify: `services/control-plane/app/api/me.py`
- Test: `tests/integration/test_connection_sync.py`

- [ ] **Step 1: Write the failing integration test for workspace connection truth**

```python
from __future__ import annotations

import httpx

from .conftest import API_URL


def _hdrs(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _delete_workspace_secret_if_present(admin_token: str, name: str) -> None:
    response = httpx.get(f"{API_URL}/admin/secrets", headers=_hdrs(admin_token), timeout=10.0)
    response.raise_for_status()
    for secret in response.json():
        if secret["name"] == name:
            delete_response = httpx.delete(
                f"{API_URL}/admin/secrets/{secret['id']}",
                headers=_hdrs(admin_token),
                timeout=10.0,
            )
            delete_response.raise_for_status()


def test_workspace_connection_requires_backing_secret(admin_token: str, user_token: str) -> None:
    _delete_workspace_secret_if_present(admin_token, "OPENAI_API_KEY")

    created = httpx.post(
        f"{API_URL}/admin/connections",
        headers=_hdrs(admin_token),
        json={
            "key": "OPENAI_API_KEY",
            "provider_key": "openai",
            "display_name": "OpenAI",
        },
        timeout=10.0,
    )
    created.raise_for_status()
    assert created.json()["status"] == "pending"

    detail = httpx.get(
        f"{API_URL}/app/catalog/hello-world",
        headers=_hdrs(user_token),
        timeout=10.0,
    )
    detail.raise_for_status()
    assert "OPENAI_API_KEY" in detail.json()["installation"]["missing_workspace_connections"]

    secret = httpx.post(
        f"{API_URL}/admin/secrets",
        headers=_hdrs(admin_token),
        json={"name": "OPENAI_API_KEY", "value": "demo-openai-key"},
        timeout=10.0,
    )
    secret.raise_for_status()

    connections = httpx.get(
        f"{API_URL}/admin/connections",
        headers=_hdrs(admin_token),
        timeout=10.0,
    )
    connections.raise_for_status()
    openai_connection = next(item for item in connections.json() if item["key"] == "OPENAI_API_KEY")
    assert openai_connection["status"] == "ready"

    ready_detail = httpx.get(
        f"{API_URL}/app/catalog/hello-world",
        headers=_hdrs(user_token),
        timeout=10.0,
    )
    ready_detail.raise_for_status()
    assert ready_detail.json()["installation"]["missing_workspace_connections"] == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/integration/test_connection_sync.py -q`
Expected: FAIL because `/admin/connections` currently returns `ready` without any stored workspace secret

- [ ] **Step 3: Change connection availability helpers to require credential backing**

```python
# services/control-plane/app/services/installations_service.py
def workspace_secret_keys(db: Session, *, tenant_id: uuid.UUID) -> set[str]:
    return {
        row.name
        for row in db.execute(
            select(Secret).where(
                Secret.tenant_id == tenant_id,
                Secret.scope == SecretScope.workspace,
                Secret.owner_user_id.is_(None),
            )
        ).scalars()
    }


def user_secret_keys(db: Session, *, tenant_id: uuid.UUID, user_id: uuid.UUID | None) -> set[str]:
    if user_id is None:
        return set()
    return {
        row.name
        for row in db.execute(
            select(Secret).where(
                Secret.tenant_id == tenant_id,
                Secret.scope == SecretScope.user,
                Secret.owner_user_id == user_id,
            )
        ).scalars()
    }


def _connection_has_backing_secret(connection: Connection, secret_keys: set[str]) -> bool:
    if connection.key in secret_keys:
        return True
    return any(secret_name in secret_keys for secret_name in connection.secret_refs_json.values())


def available_workspace_connection_keys(db: Session, *, tenant_id: uuid.UUID) -> set[str]:
    secret_keys = workspace_secret_keys(db, tenant_id=tenant_id)
    rows = db.execute(
        select(Connection).where(
            Connection.tenant_id == tenant_id,
            Connection.scope == ConnectionScope.workspace,
            Connection.user_id.is_(None),
        )
    ).scalars()
    connection_keys = {
        row.key
        for row in rows
        if row.status == ConnectionStatus.ready and _connection_has_backing_secret(row, secret_keys)
    }
    legacy_secret_only_keys = secret_keys - {
        row.key
        for row in db.execute(
            select(Connection).where(
                Connection.tenant_id == tenant_id,
                Connection.scope == ConnectionScope.workspace,
                Connection.user_id.is_(None),
            )
        ).scalars()
    }
    return connection_keys | legacy_secret_only_keys


def available_user_connection_keys(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
) -> set[str]:
    secret_keys = user_secret_keys(db, tenant_id=tenant_id, user_id=user_id)
    if user_id is None:
        return set()
    rows = db.execute(
        select(Connection).where(
            Connection.tenant_id == tenant_id,
            Connection.scope == ConnectionScope.user,
            Connection.user_id == user_id,
        )
    ).scalars()
    connection_keys = {
        row.key
        for row in rows
        if row.status == ConnectionStatus.ready and _connection_has_backing_secret(row, secret_keys)
    }
    legacy_secret_only_keys = secret_keys - {
        row.key
        for row in db.execute(
            select(Connection).where(
                Connection.tenant_id == tenant_id,
                Connection.scope == ConnectionScope.user,
                Connection.user_id == user_id,
            )
        ).scalars()
    }
    return connection_keys | legacy_secret_only_keys
```

- [ ] **Step 4: Keep metadata rows, but make secret create/rotate/delete drive readiness**

```python
# services/control-plane/app/services/installations_service.py
def _connection_by_key(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    key: str,
    scope: ConnectionScope,
    user_id: uuid.UUID | None,
) -> Connection | None:
    query = select(Connection).where(
        Connection.tenant_id == tenant_id,
        Connection.key == key,
        Connection.scope == scope,
    )
    if scope == ConnectionScope.workspace:
        query = query.where(Connection.user_id.is_(None))
    else:
        query = query.where(Connection.user_id == user_id)
    return db.execute(query).scalar_one_or_none()


def sync_connection_from_secret(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    key: str,
    scope: ConnectionScope,
    user_id: uuid.UUID | None = None,
) -> Connection:
    connection = _connection_by_key(
        db,
        tenant_id=tenant_id,
        key=key,
        scope=scope,
        user_id=user_id,
    )
    if connection is None:
        connection = Connection(
            tenant_id=tenant_id,
            user_id=user_id if scope == ConnectionScope.user else None,
            key=key,
            provider_key=infer_provider_key(key),
            scope=scope,
            status=ConnectionStatus.ready,
            display_name=key,
            scopes_json=[],
            config_json={},
            secret_refs_json={"primary": key},
        )
        db.add(connection)
        db.flush()
        return connection

    connection.status = ConnectionStatus.ready
    if not connection.secret_refs_json:
        connection.secret_refs_json = {"primary": key}
    db.flush()
    return connection


def mark_connection_pending_without_secret(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    key: str,
    scope: ConnectionScope,
    user_id: uuid.UUID | None = None,
) -> None:
    connection = _connection_by_key(
        db,
        tenant_id=tenant_id,
        key=key,
        scope=scope,
        user_id=user_id,
    )
    if connection is not None:
        connection.status = ConnectionStatus.pending
        db.flush()
```

```python
# services/control-plane/app/api/connections.py
existing_secret = secrets_service.get_workspace_secret_by_name(
    db,
    tenant_id=actor.tenant_id,
    name=payload.key,
)
next_status = ConnectionStatus.ready if payload.secret_value or existing_secret is not None else ConnectionStatus.pending

if connection is None:
    connection = Connection(
        tenant_id=actor.tenant_id,
        user_id=None,
        key=payload.key,
        provider_key=payload.provider_key or installations_service.infer_provider_key(payload.key),
        scope=ConnectionScope.workspace,
        status=next_status,
        display_name=payload.display_name or payload.key,
        scopes_json=list(payload.scopes),
        config_json=dict(payload.config),
        secret_refs_json=dict(payload.secret_refs) or {"primary": payload.key},
    )
    db.add(connection)
else:
    connection.status = next_status
    connection.secret_refs_json = dict(payload.secret_refs) or connection.secret_refs_json or {"primary": payload.key}

if payload.secret_value:
    secrets_service.upsert_workspace_secret(
        db,
        tenant_id=actor.tenant_id,
        name=payload.key,
        value=payload.secret_value,
    )
    installations_service.sync_connection_from_secret(
        db,
        tenant_id=actor.tenant_id,
        key=payload.key,
        scope=ConnectionScope.workspace,
    )
```

```python
# services/control-plane/app/api/secrets.py
secret = secrets_service.upsert_workspace_secret(
    db, tenant_id=actor.tenant_id, name=payload.name, value=payload.value
)
installations_service.sync_connection_from_secret(
    db,
    tenant_id=actor.tenant_id,
    key=payload.name,
    scope=ConnectionScope.workspace,
)
db.commit()
return WorkspaceSecretPublic.model_validate(secret)
```

```python
# services/control-plane/app/api/secrets.py delete path
rows = secrets_service.list_workspace_secrets(db, tenant_id=actor.tenant_id)
target = next((secret for secret in rows if secret.id == secret_id), None)
deleted = secrets_service.delete_workspace_secret(
    db, tenant_id=actor.tenant_id, secret_id=secret_id
)
if not deleted:
    raise HTTPException(status.HTTP_404_NOT_FOUND, "secret not found")
if target is not None:
    installations_service.mark_connection_pending_without_secret(
        db,
        tenant_id=actor.tenant_id,
        key=target.name,
        scope=ConnectionScope.workspace,
    )
db.commit()
```

```python
# services/control-plane/app/api/me.py delete path
rows = secrets_service.list_user_secrets(
    db, tenant_id=actor.tenant_id, user_id=actor.id
)
target = next((secret for secret in rows if secret.id == secret_id), None)
deleted = secrets_service.delete_user_secret(
    db, tenant_id=actor.tenant_id, user_id=actor.id, secret_id=secret_id
)
if not deleted:
    raise HTTPException(status.HTTP_404_NOT_FOUND, "secret not found")
if target is not None:
    installations_service.mark_connection_pending_without_secret(
        db,
        tenant_id=actor.tenant_id,
        user_id=actor.id,
        key=target.name,
        scope=ConnectionScope.user,
    )
db.commit()
```

- [ ] **Step 5: Make runtime connection state reflect real readiness, not row existence**

```python
# services/control-plane/app/services/installations_service.py
def build_connection_state(
    *,
    db: Session,
    descriptor: dict[str, Any],
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
) -> dict[str, dict[str, Any]]:
    workspace_secret_names = workspace_secret_keys(db, tenant_id=tenant_id)
    user_secret_names = user_secret_keys(db, tenant_id=tenant_id, user_id=user_id)
    rows = db.execute(
        select(Connection).where(
            Connection.tenant_id == tenant_id,
            (
                ((Connection.scope == ConnectionScope.workspace) & Connection.user_id.is_(None))
                | ((Connection.scope == ConnectionScope.user) & (Connection.user_id == user_id))
            ),
        )
    ).scalars().all()
    by_key = {row.key: row for row in rows}

    state: dict[str, dict[str, Any]] = {}
    for key in descriptor.get("workspace_connections", []):
        row = by_key.get(key)
        if row is None and key in workspace_secret_names:
            state[key] = {"provider_key": infer_provider_key(key), "scope": "workspace", "status": "ready", "display_name": key}
        elif row is None:
            state[key] = {"provider_key": infer_provider_key(key), "scope": "workspace", "status": "missing", "display_name": key}
        else:
            status = "ready" if row.status == ConnectionStatus.ready and _connection_has_backing_secret(row, workspace_secret_names) else "pending"
            state[key] = {"provider_key": row.provider_key, "scope": row.scope.value, "status": status, "display_name": row.display_name}

    for key in descriptor.get("user_connections", []):
        row = by_key.get(key)
        if row is None and key in user_secret_names:
            state[key] = {"provider_key": infer_provider_key(key), "scope": "user", "status": "ready", "display_name": key}
        elif row is None:
            state[key] = {"provider_key": infer_provider_key(key), "scope": "user", "status": "missing", "display_name": key}
        else:
            status = "ready" if row.status == ConnectionStatus.ready and _connection_has_backing_secret(row, user_secret_names) else "pending"
            state[key] = {"provider_key": row.provider_key, "scope": row.scope.value, "status": status, "display_name": row.display_name}

    return state
```

- [ ] **Step 6: Run the credential-backed readiness tests**

Run: `pytest tests/integration/test_connection_sync.py tests/unit/test_installation_readiness.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add services/control-plane/app/services/installations_service.py services/control-plane/app/api/connections.py services/control-plane/app/api/secrets.py services/control-plane/app/api/me.py tests/integration/test_connection_sync.py tests/unit/test_installation_readiness.py
git commit -m "fix: require stored credentials for connection readiness"
```

### Task 3: Enforce Readiness Before Manual Runs, Scheduled Runs, And Execution

**Files:**
- Create: `tests/unit/test_run_readiness.py`
- Modify: `services/control-plane/app/services/installations_service.py`
- Modify: `services/control-plane/app/api/runs.py`
- Modify: `services/control-plane/app/scheduler.py`
- Modify: `services/control-plane/app/execution/docker_backend.py`
- Modify: `tests/integration/test_installation_flow.py`
- Test: `tests/unit/test_run_readiness.py`

- [ ] **Step 1: Write the failing unit tests for readiness enforcement**

```python
import pytest

from app.services.installations_service import InstallationNotReadyError, ensure_installation_ready


def test_ensure_installation_ready_reports_all_blockers() -> None:
    summary = {
        "missing_workspace_connections": ["OPENAI_API_KEY"],
        "missing_user_connections": ["MAILBOX_TOKEN"],
        "disabled_required_modules": ["default"],
    }

    with pytest.raises(InstallationNotReadyError) as exc:
        ensure_installation_ready(summary, trigger_label="manual run")

    message = str(exc.value)
    assert "missing workspace connections: OPENAI_API_KEY" in message
    assert "missing user connections: MAILBOX_TOKEN" in message
    assert "disabled required modules: default" in message


def test_ensure_installation_ready_allows_ready_summary() -> None:
    summary = {
        "missing_workspace_connections": [],
        "missing_user_connections": [],
        "disabled_required_modules": [],
    }

    ensure_installation_ready(summary, trigger_label="scheduled run")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_run_readiness.py -q`
Expected: FAIL with `ImportError` for `InstallationNotReadyError` or `ensure_installation_ready`

- [ ] **Step 3: Add one shared readiness-enforcement helper**

```python
# services/control-plane/app/services/installations_service.py
class InstallationNotReadyError(Exception):
    """Raised when an automation installation is not ready for the requested trigger."""


def ensure_installation_ready(summary: dict[str, Any], *, trigger_label: str) -> None:
    reasons: list[str] = []
    if summary.get("missing_workspace_connections"):
        reasons.append(
            "missing workspace connections: " + ", ".join(summary["missing_workspace_connections"])
        )
    if summary.get("missing_user_connections"):
        reasons.append(
            "missing user connections: " + ", ".join(summary["missing_user_connections"])
        )
    if summary.get("disabled_required_modules"):
        reasons.append(
            "disabled required modules: " + ", ".join(summary["disabled_required_modules"])
        )
    if reasons:
        raise InstallationNotReadyError(f"{trigger_label} blocked: " + "; ".join(reasons))
```

- [ ] **Step 4: Use the shared helper in manual runs, scheduled runs, and execution-time defense**

```python
# services/control-plane/app/api/runs.py
try:
    installations_service.ensure_installation_ready(summary, trigger_label="manual run")
except installations_service.InstallationNotReadyError as e:
    raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
```

```python
# services/control-plane/app/scheduler.py
try:
    installations_service.ensure_installation_ready(summary, trigger_label="scheduled run")
except installations_service.InstallationNotReadyError as e:
    logger.warning("schedule %s skipped for agent %s: %s", sched.id, agent.slug, e)
    sched.next_run_at = croniter(sched.cron, now).get_next(datetime)
    db.commit()
    continue
```

```python
# services/control-plane/app/execution/docker_backend.py
summary = installations_service.build_installation_summary(
    descriptor=manifest,
    installation=installation,
    available_workspace_connections=installations_service.available_workspace_connection_keys(
        db, tenant_id=tenant_id
    ),
    available_user_connections=installations_service.available_user_connection_keys(
        db,
        tenant_id=tenant_id,
        user_id=run.triggering_user_id,
    ),
)
try:
    installations_service.ensure_installation_ready(summary, trigger_label="run execution")
except installations_service.InstallationNotReadyError as e:
    return self._fail(run_id, str(e))

installation_state = {
    "enabled_modules": installations_service.enabled_modules_for_installation(manifest, installation),
    "connections": installations_service.build_connection_state(
        db=db,
        descriptor=manifest,
        tenant_id=tenant_id,
        user_id=run.triggering_user_id,
    ),
    "config": installations_service.installation_config(installation),
}
```

- [ ] **Step 5: Extend the integration flow so missing user connections block manual starts**

```python
# tests/integration/test_installation_flow.py
enabled = httpx.put(
    f"{API_URL}/admin/agents/inbox-triage/installation",
    headers=_hdrs(admin_token),
    json={"enabled_modules": ["default"], "config": {}},
    timeout=10.0,
)
enabled.raise_for_status()
assert "MAILBOX_TOKEN" in enabled.json()["missing_user_connections"]

blocked_missing_connection = httpx.post(
    f"{API_URL}/runs",
    headers=_hdrs(user_token),
    json={"agent_slug": "inbox-triage", "inputs": {}},
    timeout=10.0,
)
assert blocked_missing_connection.status_code == 409
assert "missing user connections: MAILBOX_TOKEN" in blocked_missing_connection.text
```

- [ ] **Step 6: Run the readiness tests**

Run: `pytest tests/unit/test_run_readiness.py tests/integration/test_installation_flow.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add services/control-plane/app/services/installations_service.py services/control-plane/app/api/runs.py services/control-plane/app/scheduler.py services/control-plane/app/execution/docker_backend.py tests/unit/test_run_readiness.py tests/integration/test_installation_flow.py
git commit -m "fix: block unready automations before enqueue and execution"
```

## Self-Review

**1. Spec coverage:**  
Task 1 fixes Finding 1 by removing in-process imports and Finding 2 by running inspection where `platform_sdk` already exists. Task 2 fixes Finding 3 by making connection readiness depend on secret-backed credentials and syncing admin/user secret flows into connection state. Task 3 fixes Finding 4 by enforcing readiness in manual runs, scheduled runs, and execution-time fallback.

**2. Placeholder scan:**  
This plan contains no unfinished placeholder markers or cross-task omissions. Every task includes concrete files, test code, implementation code, commands, and commit messages.

**3. Type consistency:**  
The plan consistently uses `InspectionError`, `inspect_image_package`, `InstallationNotReadyError`, `ensure_installation_ready`, `sync_connection_from_secret`, and `mark_connection_pending_without_secret`. Readiness stays defined in one place: declared requirements + enabled modules + secret-backed connection availability.
