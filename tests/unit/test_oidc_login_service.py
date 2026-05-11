from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import oidc_login_service


def _provider(
    *,
    default_role: str = "user",
    role_claim: str | None = None,
    claim_role_map: dict[str, str] | None = None,
    manage_roles: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        client_id="client-123",
        scopes="openid email profile",
        discovery_url="https://example.okta.com/.well-known/openid-configuration",
        role_claim=role_claim,
        claim_role_map=dict(claim_role_map or {}),
        default_role=default_role,
        manage_roles=manage_roles,
        email_claim="email",
        is_enabled=True,
        allow_jit_provisioning=True,
        client_secret_encrypted=b"unused",
    )


def test_resolve_role_returns_default_when_no_role_claim() -> None:
    provider = _provider(default_role="developer", role_claim=None)
    assert oidc_login_service._resolve_role(provider, {"groups": ["engineering"]}) == "developer"


def test_resolve_role_uses_claim_when_string() -> None:
    provider = _provider(
        default_role="user",
        role_claim="role",
        claim_role_map={"staff": "developer", "owner": "admin"},
    )
    assert oidc_login_service._resolve_role(provider, {"role": "owner"}) == "admin"


def test_resolve_role_uses_first_matching_when_claim_is_list() -> None:
    provider = _provider(
        default_role="user",
        role_claim="groups",
        claim_role_map={"engineering": "developer", "platform-admins": "admin"},
    )
    role = oidc_login_service._resolve_role(
        provider,
        {"groups": ["random-group", "engineering", "platform-admins"]},
    )
    assert role == "developer"


def test_resolve_role_falls_back_to_default_when_no_mapping_matches() -> None:
    provider = _provider(
        default_role="user",
        role_claim="groups",
        claim_role_map={"engineering": "developer"},
    )
    assert (
        oidc_login_service._resolve_role(provider, {"groups": ["marketing", "sales"]})
        == "user"
    )


def test_select_signing_key_matches_kid() -> None:
    jwks = {"keys": [{"kid": "abc", "kty": "RSA"}, {"kid": "def", "kty": "RSA"}]}
    key = oidc_login_service._select_signing_key(jwks, {"kid": "def"})
    assert key["kid"] == "def"


def test_select_signing_key_falls_back_to_first_when_no_kid() -> None:
    jwks = {"keys": [{"kid": "abc", "kty": "RSA"}]}
    key = oidc_login_service._select_signing_key(jwks, {})
    assert key["kid"] == "abc"


def test_select_signing_key_raises_when_kid_missing() -> None:
    jwks = {"keys": [{"kid": "abc", "kty": "RSA"}]}
    with pytest.raises(oidc_login_service.OidcIdpError, match="no JWKS key"):
        oidc_login_service._select_signing_key(jwks, {"kid": "xyz"})


def test_select_signing_key_raises_when_empty() -> None:
    with pytest.raises(oidc_login_service.OidcIdpError, match="has no keys"):
        oidc_login_service._select_signing_key({"keys": []}, {})


def test_error_codes_are_stable() -> None:
    assert oidc_login_service.OidcStateError().code == "invalid_state"
    assert oidc_login_service.OidcFlowExpiredError().code == "expired_flow"
    assert oidc_login_service.OidcEmailMismatchError().code == "email_mismatch"
    assert oidc_login_service.OidcProvisioningDisabledError().code == "provisioning_disabled"
    assert oidc_login_service.OidcAccountDisabledError().code == "account_disabled"
    assert oidc_login_service.OidcIdpError().code == "idp_error"
