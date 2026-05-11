from __future__ import annotations

import httpx
import pytest

from app.services import oidc_provider_service


DISCOVERY_PAYLOAD = {
    "issuer": "https://example.okta.com",
    "authorization_endpoint": "https://example.okta.com/oauth2/v1/authorize",
    "token_endpoint": "https://example.okta.com/oauth2/v1/token",
    "jwks_uri": "https://example.okta.com/oauth2/v1/keys",
    "userinfo_endpoint": "https://example.okta.com/oauth2/v1/userinfo",
    "scopes_supported": ["openid", "email", "profile"],
    "response_types_supported": ["code"],
}


def _client_returning(payload: dict | None, *, status_code: int = 200, raise_error: Exception | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if raise_error is not None:
            raise raise_error
        if payload is None:
            return httpx.Response(status_code, text="not json")
        return httpx.Response(status_code, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_probe_discovery_returns_payload_for_valid_response() -> None:
    client = _client_returning(DISCOVERY_PAYLOAD)
    result = oidc_provider_service.probe_discovery(
        "https://example.okta.com/.well-known/openid-configuration",
        http_client=client,
    )
    assert result["issuer"] == "https://example.okta.com"


def test_probe_discovery_rejects_non_200() -> None:
    client = _client_returning(DISCOVERY_PAYLOAD, status_code=503)
    with pytest.raises(oidc_provider_service.OidcProviderValidationError, match="HTTP 503"):
        oidc_provider_service.probe_discovery(
            "https://example.okta.com/.well-known/openid-configuration",
            http_client=client,
        )


def test_probe_discovery_rejects_non_json() -> None:
    client = _client_returning(None)
    with pytest.raises(oidc_provider_service.OidcProviderValidationError, match="did not return JSON"):
        oidc_provider_service.probe_discovery(
            "https://example.okta.com/.well-known/openid-configuration",
            http_client=client,
        )


def test_probe_discovery_rejects_missing_required_fields() -> None:
    payload = dict(DISCOVERY_PAYLOAD)
    payload.pop("jwks_uri")
    client = _client_returning(payload)
    with pytest.raises(oidc_provider_service.OidcProviderValidationError, match="missing required field: jwks_uri"):
        oidc_provider_service.probe_discovery(
            "https://example.okta.com/.well-known/openid-configuration",
            http_client=client,
        )


def test_probe_discovery_reports_network_errors_as_validation() -> None:
    client = _client_returning(None, raise_error=httpx.ConnectError("dns fail"))
    with pytest.raises(oidc_provider_service.OidcProviderValidationError, match="unreachable"):
        oidc_provider_service.probe_discovery(
            "https://example.okta.com/.well-known/openid-configuration",
            http_client=client,
        )


def test_validate_default_role_rejects_unknown_role() -> None:
    with pytest.raises(oidc_provider_service.OidcProviderValidationError, match="default_role"):
        oidc_provider_service._validate_default_role("operator")


def test_validate_claim_role_map_rejects_unknown_target_role() -> None:
    with pytest.raises(oidc_provider_service.OidcProviderValidationError, match="claim_role_map"):
        oidc_provider_service._validate_claim_role_map({"engineering": "operator"})


def test_validate_claim_role_map_normalizes_values() -> None:
    cleaned = oidc_provider_service._validate_claim_role_map({"engineering": " developer "})
    assert cleaned == {"engineering": "developer"}
