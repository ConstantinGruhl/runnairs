from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.services import oidc_login_service, oidc_provider_service

from tests.integration.test_auth_sessions import (
    _complete_bootstrap,
    built_in_iam_client,
    built_in_iam_payload,
)
from tests.integration.test_oidc_login_flow import (
    CLIENT_ID,
    DISCOVERY_PAYLOAD,
    ISSUER,
    _IdpRecorder,
    _provider_payload,
    idp_mock,
    rsa_signing_keypair,
    stub_discovery,
)


def _setup_oidc(client: TestClient, payload: dict[str, str], **overrides: object) -> None:
    _complete_bootstrap(client, payload)
    response = client.put("/admin/oidc/provider", json=_provider_payload(**overrides))
    assert response.status_code == 200, response.text


def _switch_to_oidc(client: TestClient) -> None:
    response = client.put("/bootstrap/configure", json={"auth_mode": "oidc"})
    assert response.status_code == 200, response.text
    assert response.json()["auth_mode"] == "oidc"


def _drive_login(client: TestClient, recorder: _IdpRecorder, *, email: str, subject: str) -> str:
    start = client.get("/auth/oidc/start", follow_redirects=False)
    assert start.status_code == 303, start.text
    query = parse_qs(urlparse(start.headers["location"]).query)
    recorder.callback_payload = {
        "nonce": query["nonce"][0],
        "subject": subject,
        "email": email,
        "extra": {},
        "audience": CLIENT_ID,
        "issuer": ISSUER,
    }
    callback = client.get(
        "/auth/oidc/callback",
        params={"code": "code-1", "state": query["state"][0]},
        follow_redirects=False,
    )
    assert callback.status_code == 303, callback.text
    return query["state"][0]


def test_oidc_mode_blocks_built_in_login_for_non_bootstrap_users(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
    stub_discovery: None,
) -> None:
    _setup_oidc(built_in_iam_client, built_in_iam_payload)

    create_response = built_in_iam_client.post(
        "/admin/users",
        json={"email": "extra-admin@example.com", "password": "Adminpass789xyz", "role": "admin"},
    )
    assert create_response.status_code == 201

    _switch_to_oidc(built_in_iam_client)
    built_in_iam_client.post("/auth/logout")

    response = built_in_iam_client.post(
        "/auth/login",
        json={"email": "extra-admin@example.com", "password": "Adminpass789xyz"},
    )
    assert response.status_code == 423
    assert "OIDC-authoritative" in response.json()["detail"]


def test_bootstrap_admin_can_still_use_built_in_login_under_oidc_mode(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
    stub_discovery: None,
) -> None:
    _setup_oidc(built_in_iam_client, built_in_iam_payload)
    _switch_to_oidc(built_in_iam_client)
    built_in_iam_client.post("/auth/logout")

    response = built_in_iam_client.post(
        "/auth/login",
        json={
            "email": built_in_iam_payload["admin_email"],
            "password": built_in_iam_payload["admin_password"],
        },
    )
    assert response.status_code == 200


def test_hybrid_mode_allows_both_built_in_and_oidc_login(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
    stub_discovery: None,
    idp_mock: _IdpRecorder,
) -> None:
    _setup_oidc(built_in_iam_client, built_in_iam_payload)
    switch = built_in_iam_client.put("/bootstrap/configure", json={"auth_mode": "hybrid"})
    assert switch.status_code == 200
    assert switch.json()["auth_mode"] == "hybrid"

    create_response = built_in_iam_client.post(
        "/admin/users",
        json={"email": "developer.hybrid@example.com", "password": "Devpass456yzx", "role": "developer"},
    )
    assert create_response.status_code == 201

    built_in_iam_client.post("/auth/logout")
    builtin_login = built_in_iam_client.post(
        "/auth/login",
        json={"email": "developer.hybrid@example.com", "password": "Devpass456yzx"},
    )
    assert builtin_login.status_code == 200

    built_in_iam_client.post("/auth/logout")
    _drive_login(
        built_in_iam_client,
        idp_mock,
        email="hybrid-jit@example.com",
        subject="user-hybrid",
    )
    me = built_in_iam_client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"].lower() == "hybrid-jit@example.com"


def test_manage_roles_false_leaves_existing_role_unchanged(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
    stub_discovery: None,
    idp_mock: _IdpRecorder,
) -> None:
    _setup_oidc(built_in_iam_client, built_in_iam_payload, manage_roles=False)
    create = built_in_iam_client.post(
        "/admin/users",
        json={"email": "linked-role@example.com", "password": "Linkedpass123aaa", "role": "developer"},
    )
    assert create.status_code == 201
    built_in_iam_client.post("/auth/logout")

    _drive_login(
        built_in_iam_client,
        idp_mock,
        email="linked-role@example.com",
        subject="user-linked-role",
    )
    me = built_in_iam_client.get("/auth/me")
    assert me.json()["role"] == "developer"


def _drive_oidc_login_with_groups(
    client: TestClient,
    recorder: _IdpRecorder,
    *,
    email: str,
    subject: str,
    groups: list[str],
) -> None:
    start = client.get("/auth/oidc/start", follow_redirects=False)
    query = parse_qs(urlparse(start.headers["location"]).query)
    recorder.callback_payload = {
        "nonce": query["nonce"][0],
        "subject": subject,
        "email": email,
        "extra": {"groups": groups},
        "audience": CLIENT_ID,
        "issuer": ISSUER,
    }
    callback = client.get(
        "/auth/oidc/callback",
        params={"code": "fake-code", "state": query["state"][0]},
        follow_redirects=False,
    )
    assert callback.status_code == 303, callback.text


def test_manage_roles_true_updates_role_on_subsequent_login(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
    stub_discovery: None,
    idp_mock: _IdpRecorder,
) -> None:
    _setup_oidc(
        built_in_iam_client,
        built_in_iam_payload,
        manage_roles=True,
        role_claim="groups",
        claim_role_map={"engineers": "developer", "platform-admins": "admin"},
    )
    create = built_in_iam_client.post(
        "/admin/users",
        json={"email": "managed-role@example.com", "password": "Linkedpass456yyy", "role": "user"},
    )
    assert create.status_code == 201
    built_in_iam_client.post("/auth/logout")

    _drive_oidc_login_with_groups(
        built_in_iam_client,
        idp_mock,
        email="managed-role@example.com",
        subject="user-managed",
        groups=["engineers"],
    )
    first_me = built_in_iam_client.get("/auth/me")
    assert first_me.json()["role"] == "user", "first login should only link, not change role"

    built_in_iam_client.post("/auth/logout")
    _drive_oidc_login_with_groups(
        built_in_iam_client,
        idp_mock,
        email="managed-role@example.com",
        subject="user-managed",
        groups=["engineers"],
    )
    me_after = built_in_iam_client.get("/auth/me")
    assert me_after.json()["role"] == "developer", "second login should apply manage_roles"
