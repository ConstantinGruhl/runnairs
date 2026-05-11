from __future__ import annotations

from fastapi.testclient import TestClient

from tests.integration.test_bootstrap_flow import bootstrap_admin_payload, bootstrap_client


def test_normal_routes_return_bootstrap_lock_before_admin_creation(
    bootstrap_client: TestClient,
) -> None:
    response = bootstrap_client.get("/admin/diagnostics")

    assert response.status_code == 423
    assert response.json() == {
        "detail": "instance bootstrap incomplete; complete setup before using the platform",
        "bootstrap_required": True,
    }


def test_bootstrap_admin_cannot_use_normal_routes_until_completion(
    bootstrap_client: TestClient,
    bootstrap_admin_payload: dict[str, str],
) -> None:
    initialize_response = bootstrap_client.post("/bootstrap/initialize", json=bootstrap_admin_payload)
    assert initialize_response.status_code == 200

    token = initialize_response.json()["access_token"]
    response = bootstrap_client.get(
        "/admin/whoami",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 423
    assert response.json() == {
        "detail": "instance bootstrap incomplete; complete setup before using the platform",
        "bootstrap_required": True,
    }
