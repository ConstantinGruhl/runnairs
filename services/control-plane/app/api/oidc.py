from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import DbSession, require_role
from app.models import User
from app.schemas.oidc import (
    OidcDiscoveryProbeRequest,
    OidcDiscoveryProbeResponse,
    OidcProviderPublic,
    OidcProviderUpsertRequest,
)
from app.services import bootstrap_service, oidc_provider_service

router = APIRouter(prefix="/admin/oidc", tags=["oidc"])

AdminOnly = Annotated[User, Depends(require_role("admin"))]


def _build_discovery_response(payload: dict) -> OidcDiscoveryProbeResponse:
    return OidcDiscoveryProbeResponse(
        issuer=payload.get("issuer", ""),
        authorization_endpoint=payload.get("authorization_endpoint", ""),
        token_endpoint=payload.get("token_endpoint", ""),
        jwks_uri=payload.get("jwks_uri", ""),
        userinfo_endpoint=payload.get("userinfo_endpoint"),
        end_session_endpoint=payload.get("end_session_endpoint"),
        scopes_supported=list(payload.get("scopes_supported") or []),
        response_types_supported=list(payload.get("response_types_supported") or []),
    )


@router.post("/test-discovery", response_model=OidcDiscoveryProbeResponse)
def test_discovery(
    payload: OidcDiscoveryProbeRequest,
    _: AdminOnly,
) -> OidcDiscoveryProbeResponse:
    try:
        discovery = oidc_provider_service.probe_discovery(payload.discovery_url)
    except oidc_provider_service.OidcProviderValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return _build_discovery_response(discovery)


@router.get("/provider", response_model=OidcProviderPublic | None)
def get_provider(_: AdminOnly, db: DbSession) -> OidcProviderPublic | None:
    provider = oidc_provider_service.get_active_provider(db)
    if provider is None:
        return None
    return OidcProviderPublic.model_validate(oidc_provider_service.get_provider_public_view(provider))


@router.put("/provider", response_model=OidcProviderPublic)
def upsert_provider(
    payload: OidcProviderUpsertRequest,
    _: AdminOnly,
    db: DbSession,
) -> OidcProviderPublic:
    try:
        provider = oidc_provider_service.upsert_provider(
            db,
            name=payload.name,
            issuer=payload.issuer,
            discovery_url=payload.discovery_url,
            client_id=payload.client_id,
            client_secret=payload.client_secret,
            scopes=payload.scopes,
            email_claim=payload.email_claim,
            role_claim=payload.role_claim,
            claim_role_map=payload.claim_role_map,
            default_role=payload.default_role,
            allow_jit_provisioning=payload.allow_jit_provisioning,
            manage_roles=payload.manage_roles,
            is_enabled=payload.is_enabled,
            rotate_secret=payload.rotate_secret,
        )
    except oidc_provider_service.OidcProviderValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except oidc_provider_service.OidcProviderConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    db.commit()
    db.refresh(provider)
    return OidcProviderPublic.model_validate(oidc_provider_service.get_provider_public_view(provider))


@router.delete("/provider", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider(
    _: AdminOnly,
    db: DbSession,
    allow_orphaning: bool = False,
) -> None:
    provider = oidc_provider_service.get_active_provider(db)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no OIDC provider is configured")

    try:
        oidc_provider_service.delete_provider(db, provider=provider, allow_orphaning=allow_orphaning)
    except oidc_provider_service.OidcProviderConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    state = bootstrap_service.get_bootstrap_state(db)
    if state.get("auth_mode") in bootstrap_service.AUTH_MODES_REQUIRING_OIDC_PROVIDER:
        bootstrap_service.demote_auth_mode_to_built_in(db)

    db.commit()
    return None
