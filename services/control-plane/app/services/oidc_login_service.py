from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from urllib.parse import urlencode

import httpx
from fastapi import Response
from jose import jwt
from jose.exceptions import JWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    OidcAuthRequest,
    OidcProvider,
    Tenant,
    User,
    UserIdentity,
    UserRole,
    UserStatus,
)
from app.services import auth_service, oidc_provider_service

FLOW_TTL_SECONDS = 600
DEFAULT_OIDC_TIMEOUT = 10.0


def _default_http_client_factory() -> httpx.Client:
    return httpx.Client(timeout=DEFAULT_OIDC_TIMEOUT)


_HTTP_CLIENT_FACTORY = _default_http_client_factory


def _resolve_http_client(http_client: httpx.Client | None) -> tuple[httpx.Client, bool]:
    if http_client is not None:
        return http_client, False
    return _HTTP_CLIENT_FACTORY(), True


class OidcLoginError(Exception):
    """Base class for OIDC login failures with a stable client-visible code."""

    code = "unknown"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.code)


class OidcStateError(OidcLoginError):
    code = "invalid_state"


class OidcFlowExpiredError(OidcLoginError):
    code = "expired_flow"


class OidcEmailMismatchError(OidcLoginError):
    code = "email_mismatch"


class OidcProvisioningDisabledError(OidcLoginError):
    code = "provisioning_disabled"


class OidcAccountDisabledError(OidcLoginError):
    code = "account_disabled"


class OidcIdpError(OidcLoginError):
    code = "idp_error"


def start_login(
    db: Session,
    provider: OidcProvider,
    *,
    redirect_after_login: str | None = None,
    http_client: httpx.Client | None = None,
) -> tuple[str, str]:
    client, close_client = _resolve_http_client(http_client)
    try:
        discovery = oidc_provider_service.probe_discovery(
            provider.discovery_url,
            http_client=client,
        )
    finally:
        if close_client:
            client.close()
    authorization_endpoint = discovery.get("authorization_endpoint")
    if not authorization_endpoint:
        raise OidcIdpError("authorization_endpoint missing from discovery document")

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    pkce_verifier = secrets.token_urlsafe(48)
    pkce_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(pkce_verifier.encode("ascii")).digest())
        .decode("ascii")
        .rstrip("=")
    )

    flow = OidcAuthRequest(
        provider_id=provider.id,
        state=state,
        nonce=nonce,
        pkce_verifier=pkce_verifier,
        redirect_after_login=redirect_after_login,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=FLOW_TTL_SECONDS),
    )
    db.add(flow)
    db.flush()

    params = {
        "client_id": provider.client_id,
        "response_type": "code",
        "scope": provider.scopes,
        "redirect_uri": _redirect_uri(),
        "state": state,
        "nonce": nonce,
        "code_challenge": pkce_challenge,
        "code_challenge_method": "S256",
    }
    return f"{authorization_endpoint}?{urlencode(params)}", str(flow.id)


def complete_login(
    db: Session,
    provider: OidcProvider,
    *,
    flow_id: str | uuid.UUID,
    returned_state: str,
    code: str,
    response: Response,
    http_client: httpx.Client | None = None,
) -> tuple[User, str | None]:
    flow = _consume_flow(db, flow_id=flow_id)
    if flow.provider_id != provider.id:
        raise OidcStateError("flow does not belong to the active provider")
    if not secrets.compare_digest(flow.state, returned_state or ""):
        raise OidcStateError("state mismatch")

    client, close_client = _resolve_http_client(http_client)
    try:
        discovery = oidc_provider_service.probe_discovery(
            provider.discovery_url,
            http_client=client,
        )
        tokens = _exchange_code(
            provider=provider,
            token_endpoint=discovery.get("token_endpoint", ""),
            code=code,
            code_verifier=flow.pkce_verifier,
            http_client=client,
        )
        claims = _validate_id_token(
            provider=provider,
            id_token=tokens.get("id_token", ""),
            jwks_uri=discovery.get("jwks_uri", ""),
            expected_nonce=flow.nonce,
            http_client=client,
        )
    finally:
        if close_client:
            client.close()

    subject = claims.get("sub")
    if not subject:
        raise OidcIdpError("id_token missing 'sub' claim")

    email_value = claims.get(provider.email_claim)
    email = email_value.strip().lower() if isinstance(email_value, str) else None

    user = _resolve_user(db, provider, claims=claims, subject=str(subject), email=email)
    db.flush()

    token = auth_service.create_session_token(user)
    auth_service.set_session_cookie(response, token)
    return user, flow.redirect_after_login


def _consume_flow(db: Session, *, flow_id: str | uuid.UUID) -> OidcAuthRequest:
    try:
        flow_uuid = flow_id if isinstance(flow_id, uuid.UUID) else uuid.UUID(str(flow_id))
    except (TypeError, ValueError) as exc:
        raise OidcStateError("invalid flow id") from exc

    flow = db.execute(
        select(OidcAuthRequest).where(OidcAuthRequest.id == flow_uuid)
    ).scalar_one_or_none()
    if flow is None:
        raise OidcStateError("flow not found")

    db.delete(flow)
    db.flush()

    if flow.expires_at < datetime.now(timezone.utc):
        raise OidcFlowExpiredError("flow expired")
    return flow


def _exchange_code(
    *,
    provider: OidcProvider,
    token_endpoint: str,
    code: str,
    code_verifier: str,
    http_client: httpx.Client | None,
) -> dict[str, Any]:
    if not token_endpoint:
        raise OidcIdpError("token_endpoint missing from discovery document")

    client_secret = oidc_provider_service.decrypt_client_secret(provider)
    client, close_client = _resolve_http_client(http_client)
    try:
        response = client.post(
            token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _redirect_uri(),
                "client_id": provider.client_id,
                "client_secret": client_secret,
                "code_verifier": code_verifier,
            },
            headers={"Accept": "application/json"},
        )
    except httpx.HTTPError as exc:
        raise OidcIdpError(f"token exchange network error: {exc}") from exc
    finally:
        if close_client:
            client.close()

    if response.status_code != 200:
        raise OidcIdpError(f"token endpoint returned HTTP {response.status_code}")
    try:
        return response.json()
    except ValueError as exc:
        raise OidcIdpError("token endpoint did not return JSON") from exc


def _validate_id_token(
    *,
    provider: OidcProvider,
    id_token: str,
    jwks_uri: str,
    expected_nonce: str,
    http_client: httpx.Client | None,
) -> dict[str, Any]:
    if not id_token:
        raise OidcIdpError("token response missing id_token")
    if not jwks_uri:
        raise OidcIdpError("jwks_uri missing from discovery document")

    try:
        header = jwt.get_unverified_header(id_token)
    except JWTError as exc:
        raise OidcIdpError(f"id_token header invalid: {exc}") from exc

    jwks = _fetch_jwks(jwks_uri, http_client=http_client)
    key = _select_signing_key(jwks, header)
    algorithm = header.get("alg", "RS256")

    try:
        claims = jwt.decode(
            id_token,
            key,
            algorithms=[algorithm],
            audience=provider.client_id,
            issuer=provider.issuer,
        )
    except JWTError as exc:
        raise OidcIdpError(f"id_token validation failed: {exc}") from exc

    if not secrets.compare_digest(str(claims.get("nonce") or ""), expected_nonce):
        raise OidcStateError("nonce mismatch")
    return claims


def _fetch_jwks(jwks_uri: str, *, http_client: httpx.Client | None) -> dict[str, Any]:
    client, close_client = _resolve_http_client(http_client)
    try:
        response = client.get(jwks_uri)
    except httpx.HTTPError as exc:
        raise OidcIdpError(f"jwks fetch network error: {exc}") from exc
    finally:
        if close_client:
            client.close()
    if response.status_code != 200:
        raise OidcIdpError(f"jwks endpoint returned HTTP {response.status_code}")
    try:
        return response.json()
    except ValueError as exc:
        raise OidcIdpError("jwks endpoint did not return JSON") from exc


def _select_signing_key(jwks: dict[str, Any], header: dict[str, Any]) -> dict[str, Any]:
    keys: Iterable[dict[str, Any]] = jwks.get("keys") or []
    kid = header.get("kid")
    if kid:
        for key in keys:
            if key.get("kid") == kid:
                return key
        raise OidcIdpError(f"no JWKS key matches kid={kid!r}")
    keys_list = list(keys)
    if not keys_list:
        raise OidcIdpError("JWKS document has no keys")
    return keys_list[0]


def _resolve_user(
    db: Session,
    provider: OidcProvider,
    *,
    claims: dict[str, Any],
    subject: str,
    email: str | None,
) -> User:
    existing_identity = db.execute(
        select(UserIdentity).where(
            UserIdentity.provider_id == provider.id,
            UserIdentity.subject == subject,
        )
    ).scalar_one_or_none()

    if existing_identity is not None:
        linked_user = db.get(User, existing_identity.user_id)
        if linked_user is None:
            raise OidcIdpError("linked user record missing")
        if linked_user.status != UserStatus.active:
            raise OidcAccountDisabledError("linked account is disabled")
        if email and linked_user.email.lower() != email:
            raise OidcEmailMismatchError(
                "linked account email does not match the OIDC email claim"
            )

        existing_identity.last_login_at = datetime.now(timezone.utc)
        existing_identity.email_at_login = email
        if provider.manage_roles:
            resolved_role = _resolve_role(provider, claims)
            if linked_user.role.value != resolved_role:
                linked_user.role = UserRole(resolved_role)
        return linked_user

    if email:
        existing_user = db.execute(
            select(User).where(User.email.ilike(email))
        ).scalar_one_or_none()
        if existing_user is not None:
            if existing_user.status != UserStatus.active:
                raise OidcAccountDisabledError("matched account is disabled")
            identity = UserIdentity(
                user_id=existing_user.id,
                provider_id=provider.id,
                subject=subject,
                email_at_login=email,
                last_login_at=datetime.now(timezone.utc),
            )
            db.add(identity)
            return existing_user

    if not provider.allow_jit_provisioning:
        raise OidcProvisioningDisabledError(
            "provider does not allow just-in-time user provisioning"
        )
    if not email:
        raise OidcIdpError("provider claims did not include an email value for provisioning")

    tenant = db.execute(select(Tenant).order_by(Tenant.created_at)).scalars().first()
    if tenant is None:
        raise OidcIdpError("no tenant exists; cannot provision OIDC user")

    role = _resolve_role(provider, claims)
    user = User(
        tenant_id=tenant.id,
        email=email,
        password_hash=None,
        role=UserRole(role),
        status=UserStatus.active,
    )
    db.add(user)
    db.flush()

    identity = UserIdentity(
        user_id=user.id,
        provider_id=provider.id,
        subject=subject,
        email_at_login=email,
        last_login_at=datetime.now(timezone.utc),
    )
    db.add(identity)
    return user


def _resolve_role(provider: OidcProvider, claims: dict[str, Any]) -> str:
    if provider.role_claim:
        claim_value = claims.get(provider.role_claim)
        candidates: list[str] = []
        if isinstance(claim_value, list):
            candidates = [str(item) for item in claim_value]
        elif claim_value is not None:
            candidates = [str(claim_value)]
        mapping = provider.claim_role_map or {}
        for candidate in candidates:
            if candidate in mapping:
                return mapping[candidate]
    return provider.default_role


def _redirect_uri() -> str:
    base = settings.public_base_url.rstrip("/")
    return f"{base}/api/auth/oidc/callback"
