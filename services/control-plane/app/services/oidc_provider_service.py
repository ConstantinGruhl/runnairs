from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import OidcProvider, User, UserIdentity, UserRole, UserStatus
from app.services.secret_store import get_secret_store

VALID_DEFAULT_ROLES = {role.value for role in UserRole}
DISCOVERY_TIMEOUT_SECONDS = 5.0


class OidcProviderError(ValueError):
    """Raised when an OIDC provider operation cannot complete."""


class OidcProviderConflictError(OidcProviderError):
    """Raised when an OIDC provider operation conflicts with current state."""


class OidcProviderValidationError(OidcProviderError):
    """Raised when an OIDC provider configuration is invalid."""


def probe_discovery(discovery_url: str, *, http_client: httpx.Client | None = None) -> dict[str, Any]:
    client = http_client or httpx.Client(timeout=DISCOVERY_TIMEOUT_SECONDS)
    close_client = http_client is None
    try:
        response = client.get(discovery_url)
        if response.status_code != 200:
            raise OidcProviderValidationError(
                f"discovery endpoint returned HTTP {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise OidcProviderValidationError("discovery endpoint did not return JSON") from exc
    except httpx.HTTPError as exc:
        raise OidcProviderValidationError(f"discovery endpoint unreachable: {exc}") from exc
    finally:
        if close_client:
            client.close()

    for required in ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri"):
        if required not in payload:
            raise OidcProviderValidationError(
                f"discovery payload missing required field: {required}"
            )
    return payload


def get_active_provider(db: Session) -> OidcProvider | None:
    return db.execute(select(OidcProvider).order_by(OidcProvider.created_at)).scalars().first()


def get_provider_public_view(provider: OidcProvider) -> dict[str, Any]:
    return {
        "id": provider.id,
        "name": provider.name,
        "issuer": provider.issuer,
        "discovery_url": provider.discovery_url,
        "client_id": provider.client_id,
        "has_client_secret": bool(provider.client_secret_encrypted),
        "scopes": provider.scopes,
        "email_claim": provider.email_claim,
        "role_claim": provider.role_claim,
        "claim_role_map": dict(provider.claim_role_map or {}),
        "default_role": provider.default_role,
        "allow_jit_provisioning": provider.allow_jit_provisioning,
        "manage_roles": provider.manage_roles,
        "is_enabled": provider.is_enabled,
        "created_at": provider.created_at,
        "updated_at": provider.updated_at,
    }


def _validate_default_role(default_role: str) -> str:
    value = (default_role or "").strip()
    if value not in VALID_DEFAULT_ROLES:
        raise OidcProviderValidationError(
            f"default_role must be one of {sorted(VALID_DEFAULT_ROLES)}; got {value!r}"
        )
    return value


def _validate_claim_role_map(claim_role_map: dict[str, str]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for claim_value, role_value in (claim_role_map or {}).items():
        role = (role_value or "").strip()
        if role not in VALID_DEFAULT_ROLES:
            raise OidcProviderValidationError(
                f"claim_role_map value for {claim_value!r} must be one of "
                f"{sorted(VALID_DEFAULT_ROLES)}; got {role_value!r}"
            )
        cleaned[claim_value] = role
    return cleaned


def upsert_provider(
    db: Session,
    *,
    name: str,
    issuer: str,
    discovery_url: str,
    client_id: str,
    client_secret: str | None,
    scopes: str,
    email_claim: str,
    role_claim: str | None,
    claim_role_map: dict[str, str],
    default_role: str,
    allow_jit_provisioning: bool,
    manage_roles: bool,
    is_enabled: bool,
    rotate_secret: bool,
    http_client: httpx.Client | None = None,
) -> OidcProvider:
    default_role = _validate_default_role(default_role)
    claim_role_map = _validate_claim_role_map(claim_role_map)
    probe_discovery(discovery_url, http_client=http_client)

    provider = get_active_provider(db)
    if provider is None:
        if not client_secret:
            raise OidcProviderValidationError("client_secret is required when creating a provider")
        encrypted = get_secret_store().encrypt(client_secret)
        provider = OidcProvider(
            name=name,
            issuer=issuer,
            discovery_url=discovery_url,
            client_id=client_id,
            client_secret_encrypted=encrypted,
            scopes=scopes,
            email_claim=email_claim,
            role_claim=role_claim,
            claim_role_map=claim_role_map,
            default_role=default_role,
            allow_jit_provisioning=allow_jit_provisioning,
            manage_roles=manage_roles,
            is_enabled=is_enabled,
        )
        db.add(provider)
        db.flush()
        return provider

    provider.name = name
    provider.issuer = issuer
    provider.discovery_url = discovery_url
    provider.client_id = client_id
    provider.scopes = scopes
    provider.email_claim = email_claim
    provider.role_claim = role_claim
    provider.claim_role_map = claim_role_map
    provider.default_role = default_role
    provider.allow_jit_provisioning = allow_jit_provisioning
    provider.manage_roles = manage_roles
    provider.is_enabled = is_enabled
    provider.updated_at = datetime.now(timezone.utc)

    if rotate_secret:
        if not client_secret:
            raise OidcProviderValidationError("rotate_secret requires a non-empty client_secret")
        provider.client_secret_encrypted = get_secret_store().encrypt(client_secret)
    elif client_secret:
        raise OidcProviderValidationError(
            "client_secret was provided without rotate_secret=True; set rotate_secret=True to replace it"
        )

    db.flush()
    return provider


def decrypt_client_secret(provider: OidcProvider) -> str:
    if not provider.client_secret_encrypted:
        raise OidcProviderError("provider has no client secret stored")
    return get_secret_store().decrypt(provider.client_secret_encrypted)


def delete_provider(
    db: Session,
    *,
    provider: OidcProvider,
    allow_orphaning: bool,
) -> None:
    oidc_only_count = db.execute(
        select(func.count(User.id))
        .join(UserIdentity, UserIdentity.user_id == User.id)
        .where(
            UserIdentity.provider_id == provider.id,
            User.password_hash.is_(None),
            User.status == UserStatus.active,
        )
    ).scalar_one()
    if oidc_only_count and not allow_orphaning:
        raise OidcProviderConflictError(
            f"refusing to delete provider while {oidc_only_count} OIDC-only user(s) still depend on it; "
            "set allow_orphaning=true to override"
        )
    db.delete(provider)
    db.flush()
