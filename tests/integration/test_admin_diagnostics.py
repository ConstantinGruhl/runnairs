from __future__ import annotations

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
