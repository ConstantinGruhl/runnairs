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
