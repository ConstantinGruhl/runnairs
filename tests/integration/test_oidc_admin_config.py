from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services import oidc_provider_service

from tests.integration.test_auth_sessions import (
    _complete_bootstrap,
    built_in_iam_client,
    built_in_iam_payload,
)


DISCOVERY_PAYLOAD = {
    "issuer": "https://example.okta.com",
    "authorization_endpoint": "https://example.okta.com/oauth2/v1/authorize",
    "token_endpoint": "https://example.okta.com/oauth2/v1/token",
    "jwks_uri": "https://example.okta.com/oauth2/v1/keys",
    "userinfo_endpoint": "https://example.okta.com/oauth2/v1/userinfo",
    "scopes_supported": ["openid", "email", "profile"],
    "response_types_supported": ["code"],
}


@pytest.fixture
def stub_discovery(monkeypatch: pytest.MonkeyPatch):
    def _stub(discovery_url: str, *, http_client=None):
        return dict(DISCOVERY_PAYLOAD)

    monkeypatch.setattr(oidc_provider_service, "probe_discovery", _stub)


def _provider_payload(**overrides: object) -> dict:
    payload = {
        "name": "Okta",
        "issuer": "https://example.okta.com",
        "discovery_url": "https://example.okta.com/.well-known/openid-configuration",
        "client_id": "client-123",
        "client_secret": "super-secret-value",
        "scopes": "openid email profile",
        "email_claim": "email",
        "role_claim": "groups",
        "claim_role_map": {"engineers": "developer"},
        "default_role": "user",
        "allow_jit_provisioning": True,
        "manage_roles": False,
        "is_enabled": True,
        "rotate_secret": False,
    }
    payload.update(overrides)
    return payload


def test_admin_can_create_fetch_update_and_delete_provider(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
    stub_discovery: None,
) -> None:
    _complete_bootstrap(built_in_iam_client, built_in_iam_payload)

    initial = built_in_iam_client.get("/admin/oidc/provider")
    assert initial.status_code == 200
    assert initial.json() is None

    create_response = built_in_iam_client.put(
        "/admin/oidc/provider",
        json=_provider_payload(),
    )
    assert create_response.status_code == 200
    provider = create_response.json()
    assert provider["client_id"] == "client-123"
    assert provider["has_client_secret"] is True
    assert "client_secret" not in provider
    assert "client_secret_encrypted" not in provider

    update_response = built_in_iam_client.put(
        "/admin/oidc/provider",
        json=_provider_payload(name="Okta Prod", is_enabled=False, client_secret=None),
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Okta Prod"
    assert update_response.json()["is_enabled"] is False

    delete_response = built_in_iam_client.delete("/admin/oidc/provider")
    assert delete_response.status_code == 204

    follow_up = built_in_iam_client.get("/admin/oidc/provider")
    assert follow_up.json() is None


def test_non_admin_cannot_manage_provider(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
    stub_discovery: None,
) -> None:
    _complete_bootstrap(built_in_iam_client, built_in_iam_payload)

    create_user = built_in_iam_client.post(
        "/admin/users",
        json={"email": "dev@example.com", "password": "Developerpass123", "role": "developer"},
    )
    assert create_user.status_code == 201

    built_in_iam_client.post("/auth/logout")
    login = built_in_iam_client.post(
        "/auth/login",
        json={"email": "dev@example.com", "password": "Developerpass123"},
    )
    assert login.status_code == 200

    response = built_in_iam_client.put(
        "/admin/oidc/provider",
        json=_provider_payload(),
    )
    assert response.status_code == 403


def test_invalid_discovery_url_returns_422(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _complete_bootstrap(built_in_iam_client, built_in_iam_payload)

    def _stub(discovery_url: str, *, http_client=None):
        raise oidc_provider_service.OidcProviderValidationError("discovery endpoint unreachable")

    monkeypatch.setattr(oidc_provider_service, "probe_discovery", _stub)

    response = built_in_iam_client.put(
        "/admin/oidc/provider",
        json=_provider_payload(),
    )
    assert response.status_code == 422
    assert "unreachable" in response.json()["detail"]


def test_secret_replacement_requires_rotate_flag(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
    stub_discovery: None,
) -> None:
    _complete_bootstrap(built_in_iam_client, built_in_iam_payload)

    create_response = built_in_iam_client.put(
        "/admin/oidc/provider",
        json=_provider_payload(),
    )
    assert create_response.status_code == 200

    no_rotate = built_in_iam_client.put(
        "/admin/oidc/provider",
        json=_provider_payload(client_secret="new-secret-without-rotate", rotate_secret=False),
    )
    assert no_rotate.status_code == 422
    assert "rotate_secret" in no_rotate.json()["detail"]

    rotated = built_in_iam_client.put(
        "/admin/oidc/provider",
        json=_provider_payload(client_secret="new-secret-rotated", rotate_secret=True),
    )
    assert rotated.status_code == 200


def test_delete_demotes_auth_mode_when_oidc_was_active(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
    stub_discovery: None,
) -> None:
    _complete_bootstrap(built_in_iam_client, built_in_iam_payload)

    built_in_iam_client.put("/admin/oidc/provider", json=_provider_payload())
    configure_response = built_in_iam_client.put(
        "/bootstrap/configure",
        json={"auth_mode": "oidc"},
    )
    assert configure_response.status_code == 200
    assert configure_response.json()["auth_mode"] == "oidc"

    delete_response = built_in_iam_client.delete("/admin/oidc/provider")
    assert delete_response.status_code == 204

    state = built_in_iam_client.get("/bootstrap/state").json()
    assert state["auth_mode"] == "built_in"


def test_test_discovery_endpoint_returns_metadata(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
    stub_discovery: None,
) -> None:
    _complete_bootstrap(built_in_iam_client, built_in_iam_payload)

    response = built_in_iam_client.post(
        "/admin/oidc/test-discovery",
        json={"discovery_url": "https://example.okta.com/.well-known/openid-configuration"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["issuer"] == "https://example.okta.com"
    assert body["jwks_uri"] == "https://example.okta.com/oauth2/v1/keys"
