from __future__ import annotations

import time

import httpx
import pytest

from .conftest import API_URL


def _hdrs(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _wait_for_status(token: str, run_id: str, *targets: str, timeout: float = 90.0) -> dict:
    deadline = time.time() + timeout
    last: dict | None = None
    while time.time() < deadline:
        response = httpx.get(f"{API_URL}/runs/{run_id}", headers=_hdrs(token), timeout=10.0)
        response.raise_for_status()
        last = response.json()
        if last["status"] in targets:
            return last
        time.sleep(1)
    pytest.fail(f"run {run_id} never reached one of {targets}; last={last}")


def test_installation_flow(admin_token: str, user_token: str) -> None:
    catalog = httpx.get(f"{API_URL}/app/catalog", headers=_hdrs(user_token), timeout=10.0).json()
    slugs = [agent["slug"] for agent in catalog["agents"]]
    if "inbox-triage" not in slugs:
        pytest.skip("inbox-triage is not deployed in this environment")

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

    connection_list = httpx.get(
        f"{API_URL}/admin/connections",
        headers=_hdrs(admin_token),
        timeout=10.0,
    )
    connection_list.raise_for_status()
    assert any(item["key"] == "OPENAI_API_KEY" for item in connection_list.json())

    disabled = httpx.put(
        f"{API_URL}/admin/agents/inbox-triage/installation",
        headers=_hdrs(admin_token),
        json={"enabled_modules": [], "config": {}},
        timeout=10.0,
    )
    disabled.raise_for_status()
    assert disabled.json()["disabled_required_modules"] == ["default"]

    blocked_start = httpx.post(
        f"{API_URL}/runs",
        headers=_hdrs(user_token),
        json={"agent_slug": "inbox-triage", "inputs": {}},
        timeout=10.0,
    )
    assert blocked_start.status_code == 409
    assert "required modules" in blocked_start.text

    enabled = httpx.put(
        f"{API_URL}/admin/agents/inbox-triage/installation",
        headers=_hdrs(admin_token),
        json={"enabled_modules": ["default"], "config": {}},
        timeout=10.0,
    )
    enabled.raise_for_status()
    assert "MAILBOX_TOKEN" in enabled.json()["missing_user_connections"]

    connected = httpx.post(
        f"{API_URL}/me/secrets",
        headers=_hdrs(user_token),
        json={"name": "MAILBOX_TOKEN", "value": "demo-mailbox-token"},
        timeout=10.0,
    )
    connected.raise_for_status()

    detail = httpx.get(
        f"{API_URL}/app/catalog/inbox-triage",
        headers=_hdrs(user_token),
        timeout=10.0,
    )
    detail.raise_for_status()
    body = detail.json()
    assert body["installation"]["ready"] is True
    assert body["installation"]["missing_user_connections"] == []
    assert body["installation"]["enabled_modules"] == ["default"]

    started = httpx.post(
        f"{API_URL}/runs",
        headers=_hdrs(user_token),
        json={"agent_slug": "inbox-triage", "inputs": {}},
        timeout=10.0,
    )
    started.raise_for_status()
    run_id = started.json()["id"]

    run = _wait_for_status(user_token, run_id, "succeeded", timeout=90.0)
    assert run["status"] == "succeeded"
