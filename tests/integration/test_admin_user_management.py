from __future__ import annotations

from fastapi.testclient import TestClient

from tests.integration.test_auth_sessions import (
    _complete_bootstrap,
    built_in_iam_client,
    built_in_iam_payload,
)


def test_admin_can_create_user_and_change_role(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
) -> None:
    _complete_bootstrap(built_in_iam_client, built_in_iam_payload)

    create_response = built_in_iam_client.post(
        "/admin/users",
        json={
            "email": "developer.one@example.com",
            "password": "Developerpass123",
            "role": "developer",
        },
    )

    assert create_response.status_code == 201
    created_user = create_response.json()
    assert created_user["status"] == "active"
    assert created_user["role"] == "developer"

    update_response = built_in_iam_client.patch(
        f"/admin/users/{created_user['id']}",
        json={"role": "user"},
    )

    assert update_response.status_code == 200
    assert update_response.json()["role"] == "user"


def test_disabled_users_cannot_authenticate(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
) -> None:
    _complete_bootstrap(built_in_iam_client, built_in_iam_payload)

    create_response = built_in_iam_client.post(
        "/admin/users",
        json={
            "email": "disabled.user@example.com",
            "password": "Disabledpass123",
            "role": "user",
        },
    )
    assert create_response.status_code == 201
    created_user = create_response.json()

    disable_response = built_in_iam_client.patch(
        f"/admin/users/{created_user['id']}",
        json={"status": "disabled"},
    )
    assert disable_response.status_code == 200
    assert disable_response.json()["status"] == "disabled"

    login_response = built_in_iam_client.post(
        "/auth/login",
        json={
            "email": "disabled.user@example.com",
            "password": "Disabledpass123",
        },
    )
    assert login_response.status_code == 401


def test_admin_can_issue_password_reset_code_without_db_edits(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
) -> None:
    _complete_bootstrap(built_in_iam_client, built_in_iam_payload)

    create_response = built_in_iam_client.post(
        "/admin/users",
        json={
            "email": "reset.user@example.com",
            "password": "Starterpass123",
            "role": "developer",
        },
    )
    assert create_response.status_code == 201
    created_user = create_response.json()

    reset_response = built_in_iam_client.post(f"/admin/users/{created_user['id']}/password-reset")
    assert reset_response.status_code == 200
    reset_payload = reset_response.json()
    assert reset_payload["kind"] == "password_reset"
    assert reset_payload["expires_at"] is not None

    complete_response = built_in_iam_client.post(
        "/auth/password-reset/complete",
        json={
            "email": "reset.user@example.com",
            "reset_code": reset_payload["code"],
            "new_password": "Updatedpass456",
        },
    )
    assert complete_response.status_code == 200

    failed_old_login = built_in_iam_client.post(
        "/auth/login",
        json={
            "email": "reset.user@example.com",
            "password": "Starterpass123",
        },
    )
    assert failed_old_login.status_code == 401

    new_login = built_in_iam_client.post(
        "/auth/login",
        json={
            "email": "reset.user@example.com",
            "password": "Updatedpass456",
        },
    )
    assert new_login.status_code == 200
