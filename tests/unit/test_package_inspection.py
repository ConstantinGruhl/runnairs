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
