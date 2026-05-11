from __future__ import annotations

import base64
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient
from jose import jwt

from app.services import oidc_login_service, oidc_provider_service

from tests.integration.test_auth_sessions import (
    _complete_bootstrap,
    built_in_iam_client,
    built_in_iam_payload,
)


ISSUER = "https://example.okta.com"
TOKEN_ENDPOINT = f"{ISSUER}/oauth2/v1/token"
JWKS_URI = f"{ISSUER}/oauth2/v1/keys"
AUTHORIZATION_ENDPOINT = f"{ISSUER}/oauth2/v1/authorize"
CLIENT_ID = "client-123"

DISCOVERY_PAYLOAD: dict[str, Any] = {
    "issuer": ISSUER,
    "authorization_endpoint": AUTHORIZATION_ENDPOINT,
    "token_endpoint": TOKEN_ENDPOINT,
    "jwks_uri": JWKS_URI,
    "userinfo_endpoint": f"{ISSUER}/oauth2/v1/userinfo",
    "scopes_supported": ["openid", "email", "profile"],
    "response_types_supported": ["code"],
}


def _b64url_uint(value: int) -> str:
    length = (value.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(value.to_bytes(length, "big")).decode("ascii").rstrip("=")


@pytest.fixture(scope="module")
def rsa_signing_keypair() -> tuple[str, dict[str, Any]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_numbers = private_key.public_key().public_numbers()
    jwk = {
        "kty": "RSA",
        "kid": "test-key-1",
        "alg": "RS256",
        "use": "sig",
        "n": _b64url_uint(public_numbers.n),
        "e": _b64url_uint(public_numbers.e),
    }
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    return private_pem, jwk


def _sign_id_token(
    private_pem: str,
    *,
    kid: str,
    nonce: str,
    subject: str,
    email: str,
    extra: dict[str, Any] | None = None,
    audience: str = CLIENT_ID,
    issuer: str = ISSUER,
) -> str:
    now = int(time.time())
    payload = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "email": email,
        "nonce": nonce,
        "iat": now,
        "exp": now + 3600,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": kid})


class _IdpRecorder:
    def __init__(self) -> None:
        self.token_requests: list[dict[str, str]] = []
        self.callback_payload: dict[str, str] | None = None


@pytest.fixture
def stub_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    def _stub(discovery_url: str, *, http_client: httpx.Client | None = None) -> dict:
        return dict(DISCOVERY_PAYLOAD)

    monkeypatch.setattr(oidc_provider_service, "probe_discovery", _stub)


@pytest.fixture
def idp_mock(
    monkeypatch: pytest.MonkeyPatch,
    rsa_signing_keypair: tuple[str, dict],
) -> _IdpRecorder:
    private_pem, jwk = rsa_signing_keypair
    recorder = _IdpRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == JWKS_URI:
            return httpx.Response(200, json={"keys": [jwk]})
        if url == TOKEN_ENDPOINT:
            form = dict(parse_qs(request.content.decode("utf-8")))
            simple = {key: value[0] for key, value in form.items()}
            recorder.token_requests.append(simple)
            payload = recorder.callback_payload or {}
            nonce = payload.get("nonce", "missing-nonce")
            id_token = _sign_id_token(
                private_pem,
                kid=jwk["kid"],
                nonce=nonce,
                subject=payload.get("subject", "abc123"),
                email=payload.get("email", "alice@example.com"),
                extra=payload.get("extra"),
                audience=payload.get("audience", CLIENT_ID),
                issuer=payload.get("issuer", ISSUER),
            )
            return httpx.Response(
                200,
                json={
                    "access_token": "fake-access",
                    "id_token": id_token,
                    "token_type": "Bearer",
                    "expires_in": 3600,
                },
            )
        return httpx.Response(404, text=f"unmocked URL: {url}")

    def factory() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(oidc_login_service, "_HTTP_CLIENT_FACTORY", factory)
    return recorder


def _provider_payload(**overrides: object) -> dict:
    payload = {
        "name": "Okta",
        "issuer": ISSUER,
        "discovery_url": f"{ISSUER}/.well-known/openid-configuration",
        "client_id": CLIENT_ID,
        "client_secret": "super-secret-value",
        "scopes": "openid email profile",
        "email_claim": "email",
        "role_claim": "groups",
        "claim_role_map": {"engineers": "developer", "admins": "admin"},
        "default_role": "user",
        "allow_jit_provisioning": True,
        "manage_roles": False,
        "is_enabled": True,
        "rotate_secret": False,
    }
    payload.update(overrides)
    return payload


def _setup_oidc(client: TestClient, payload: dict[str, str], **provider_overrides: object) -> None:
    _complete_bootstrap(client, payload)
    response = client.put("/admin/oidc/provider", json=_provider_payload(**provider_overrides))
    assert response.status_code == 200, response.text


def _drive_flow(
    client: TestClient,
    recorder: _IdpRecorder,
    *,
    email: str = "alice@example.com",
    subject: str = "user-123",
    extra: dict[str, Any] | None = None,
    audience: str = CLIENT_ID,
    issuer: str = ISSUER,
) -> httpx.Response:
    start = client.get("/auth/oidc/start", follow_redirects=False)
    assert start.status_code == 303, start.text
    auth_url = start.headers["location"]
    parsed = urlparse(auth_url)
    query = {key: value[0] for key, value in parse_qs(parsed.query).items()}
    recorder.callback_payload = {
        "nonce": query["nonce"],
        "subject": subject,
        "email": email,
        "extra": extra or {},
        "audience": audience,
        "issuer": issuer,
    }
    callback = client.get(
        "/auth/oidc/callback",
        params={"code": "fake-code", "state": query["state"]},
        follow_redirects=False,
    )
    return callback


def test_status_reports_enabled_after_provider_setup(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
    stub_discovery: None,
) -> None:
    _setup_oidc(built_in_iam_client, built_in_iam_payload)

    response = built_in_iam_client.get("/auth/oidc/status")
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["provider_name"] == "Okta"
    assert body["login_url"] == "/api/auth/oidc/start"
    assert body["built_in_login_enabled"] is True


def test_start_sets_flow_cookie_and_redirects_to_idp(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
    stub_discovery: None,
) -> None:
    _setup_oidc(built_in_iam_client, built_in_iam_payload)

    response = built_in_iam_client.get(
        "/auth/oidc/start",
        params={"next": "/admin"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    auth_url = response.headers["location"]
    assert auth_url.startswith(AUTHORIZATION_ENDPOINT + "?")
    cookies = response.headers.get_list("set-cookie")
    assert any(cookie.startswith("oidc_flow=") for cookie in cookies)
    query = parse_qs(urlparse(auth_url).query)
    assert query["client_id"] == [CLIENT_ID]
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert "code_challenge" in query
    assert "nonce" in query
    assert "state" in query


def test_callback_provisions_new_user_and_sets_session_cookie(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
    stub_discovery: None,
    idp_mock: _IdpRecorder,
) -> None:
    _setup_oidc(built_in_iam_client, built_in_iam_payload)
    built_in_iam_client.post("/auth/logout")

    response = _drive_flow(built_in_iam_client, idp_mock, email="alice@example.com")
    assert response.status_code == 303
    assert "platform_session=" in response.headers.get("set-cookie", "")

    me = built_in_iam_client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"].lower() == "alice@example.com"


def test_callback_with_audience_mismatch_redirects_with_error(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
    stub_discovery: None,
    idp_mock: _IdpRecorder,
) -> None:
    _setup_oidc(built_in_iam_client, built_in_iam_payload)
    built_in_iam_client.post("/auth/logout")

    response = _drive_flow(
        built_in_iam_client,
        idp_mock,
        audience="someone-else",
    )
    assert response.status_code == 303
    assert "/login?oidc_error=" in response.headers["location"]


def test_replay_of_consumed_state_is_rejected(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
    stub_discovery: None,
    idp_mock: _IdpRecorder,
) -> None:
    _setup_oidc(built_in_iam_client, built_in_iam_payload)
    built_in_iam_client.post("/auth/logout")

    start = built_in_iam_client.get("/auth/oidc/start", follow_redirects=False)
    auth_url = start.headers["location"]
    query = parse_qs(urlparse(auth_url).query)
    idp_mock.callback_payload = {
        "nonce": query["nonce"][0],
        "subject": "user-replay",
        "email": "replay@example.com",
        "extra": {},
        "audience": CLIENT_ID,
        "issuer": ISSUER,
    }

    first = built_in_iam_client.get(
        "/auth/oidc/callback",
        params={"code": "code-1", "state": query["state"][0]},
        follow_redirects=False,
    )
    assert first.status_code == 303
    assert "platform_session=" in first.headers.get("set-cookie", "")
    built_in_iam_client.post("/auth/logout")

    second = built_in_iam_client.get(
        "/auth/oidc/callback",
        params={"code": "code-1", "state": query["state"][0]},
        follow_redirects=False,
    )
    assert second.status_code == 303
    assert "oidc_error=invalid_state" in second.headers["location"]


def test_callback_links_existing_user_by_email(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
    stub_discovery: None,
    idp_mock: _IdpRecorder,
) -> None:
    _setup_oidc(built_in_iam_client, built_in_iam_payload)
    # admin creates a local developer with the same email the IdP will return
    create_response = built_in_iam_client.post(
        "/admin/users",
        json={
            "email": "linked@example.com",
            "password": "Linkedpass123",
            "role": "developer",
        },
    )
    assert create_response.status_code == 201
    built_in_iam_client.post("/auth/logout")

    response = _drive_flow(
        built_in_iam_client,
        idp_mock,
        email="linked@example.com",
        subject="user-linked",
    )
    assert response.status_code == 303

    me = built_in_iam_client.get("/auth/me")
    assert me.status_code == 200
    me_body = me.json()
    assert me_body["email"].lower() == "linked@example.com"
    assert me_body["role"] == "developer"


def test_callback_provisioning_disabled_returns_error(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
    stub_discovery: None,
    idp_mock: _IdpRecorder,
) -> None:
    _setup_oidc(built_in_iam_client, built_in_iam_payload, allow_jit_provisioning=False)
    built_in_iam_client.post("/auth/logout")

    response = _drive_flow(
        built_in_iam_client,
        idp_mock,
        email="newperson@example.com",
        subject="user-new",
    )
    assert response.status_code == 303
    assert "oidc_error=provisioning_disabled" in response.headers["location"]
