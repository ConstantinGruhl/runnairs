from __future__ import annotations

from fastapi.testclient import TestClient

from tests.integration.test_auth_sessions import built_in_iam_client, built_in_iam_payload


def test_fresh_deployment_can_choose_built_in_iam_and_complete_setup(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
) -> None:
    state_response = built_in_iam_client.get("/bootstrap/state")
    assert state_response.status_code == 200
    state_payload = state_response.json()
    assert state_payload["auth_mode"] is None
    assert state_payload["supported_auth_modes"] == ["built_in"]

    initialize_response = built_in_iam_client.post("/bootstrap/initialize", json=built_in_iam_payload)
    assert initialize_response.status_code == 200
    initialize_payload = initialize_response.json()
    assert initialize_payload["state"]["auth_mode"] == "built_in"
    assert initialize_payload["bootstrap_recovery_code"]

    complete_response = built_in_iam_client.post(
        "/bootstrap/complete",
        headers={"Authorization": f"Bearer {initialize_payload['access_token']}"},
    )
    assert complete_response.status_code == 200
    assert complete_response.json()["completed"] is True

    me_response = built_in_iam_client.get("/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["email"] == built_in_iam_payload["admin_email"]


def test_bootstrap_admin_recovery_flow_is_documented_and_works_after_setup(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
) -> None:
    initialize_response = built_in_iam_client.post("/bootstrap/initialize", json=built_in_iam_payload)
    assert initialize_response.status_code == 200
    initialize_payload = initialize_response.json()
    recovery_code = initialize_payload["bootstrap_recovery_code"]

    complete_response = built_in_iam_client.post(
        "/bootstrap/complete",
        headers={"Authorization": f"Bearer {initialize_payload['access_token']}"},
    )
    assert complete_response.status_code == 200

    recovery_response = built_in_iam_client.post(
        "/auth/recovery/complete",
        json={
            "email": built_in_iam_payload["admin_email"],
            "recovery_code": recovery_code,
            "new_password": "Recoveredpass456",
        },
    )
    assert recovery_response.status_code == 200

    stale_login = built_in_iam_client.post(
        "/auth/login",
        json={
          "email": built_in_iam_payload["admin_email"],
          "password": built_in_iam_payload["admin_password"],
        },
    )
    assert stale_login.status_code == 401

    fresh_login = built_in_iam_client.post(
        "/auth/login",
        json={
            "email": built_in_iam_payload["admin_email"],
            "password": "Recoveredpass456",
        },
    )
    assert fresh_login.status_code == 200
