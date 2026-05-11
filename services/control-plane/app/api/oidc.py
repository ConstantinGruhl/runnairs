from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.core.config import settings
from app.core.dependencies import DbSession, require_role
from app.models import User
from app.schemas.oidc import (
    OidcDiscoveryProbeRequest,
    OidcDiscoveryProbeResponse,
    OidcProviderPublic,
    OidcProviderUpsertRequest,
)
from app.services import bootstrap_service, oidc_login_service, oidc_provider_service

router = APIRouter(prefix="/admin/oidc", tags=["oidc"])
auth_router = APIRouter(prefix="/auth/oidc", tags=["oidc-login"])

OIDC_FLOW_COOKIE = "oidc_flow"
OIDC_FLOW_COOKIE_MAX_AGE = 600

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


class OidcStatusResponse(BaseModel):
    enabled: bool
    provider_name: str | None
    login_url: str | None
    auth_mode: str | None
    built_in_login_enabled: bool


@auth_router.get("/status", response_model=OidcStatusResponse)
def oidc_status(db: DbSession) -> OidcStatusResponse:
    provider = oidc_provider_service.get_active_provider(db)
    state = bootstrap_service.get_bootstrap_state(db)
    enabled = bool(provider and provider.is_enabled)
    return OidcStatusResponse(
        enabled=enabled,
        provider_name=provider.name if enabled else None,
        login_url="/api/auth/oidc/start" if enabled else None,
        auth_mode=state.get("auth_mode"),
        built_in_login_enabled=bool(state.get("built_in_login_enabled", True)),
    )


def _safe_redirect_target(candidate: str | None) -> str | None:
    if not candidate:
        return None
    if not candidate.startswith("/") or candidate.startswith("//"):
        return None
    return candidate


def _is_production_cookie() -> bool:
    return settings.app_env.lower() == "production"


@auth_router.get("/start")
def start_oidc_login(db: DbSession, next: str | None = None) -> RedirectResponse:
    provider = oidc_provider_service.get_active_provider(db)
    if provider is None or not provider.is_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "no OIDC provider is enabled")

    try:
        auth_url, flow_id = oidc_login_service.start_login(
            db,
            provider,
            redirect_after_login=_safe_redirect_target(next),
        )
    except oidc_login_service.OidcLoginError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, exc.code) from exc

    db.commit()
    response = RedirectResponse(auth_url, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=OIDC_FLOW_COOKIE,
        value=flow_id,
        httponly=True,
        secure=_is_production_cookie(),
        samesite="lax",
        max_age=OIDC_FLOW_COOKIE_MAX_AGE,
        path="/",
    )
    return response


def _login_error_redirect(code: str) -> RedirectResponse:
    response = RedirectResponse(
        f"/login?oidc_error={code}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    response.delete_cookie(OIDC_FLOW_COOKIE, path="/")
    return response


@auth_router.get("/callback")
def oidc_callback(
    request: Request,
    db: DbSession,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    flow_id = request.cookies.get(OIDC_FLOW_COOKIE)
    if error:
        return _login_error_redirect("idp_error")
    if not flow_id:
        return _login_error_redirect("invalid_state")
    if not code or not state:
        return _login_error_redirect("invalid_state")

    provider = oidc_provider_service.get_active_provider(db)
    if provider is None or not provider.is_enabled:
        return _login_error_redirect("provider_disabled")

    response = RedirectResponse(status_code=status.HTTP_303_SEE_OTHER, url="/")
    try:
        user, redirect_after = oidc_login_service.complete_login(
            db,
            provider,
            flow_id=flow_id,
            returned_state=state,
            code=code,
            response=response,
        )
    except oidc_login_service.OidcLoginError as exc:
        db.rollback()
        return _login_error_redirect(exc.code)

    db.commit()
    target = _safe_redirect_target(redirect_after) or "/"
    response.headers["location"] = target
    response.delete_cookie(OIDC_FLOW_COOKIE, path="/")
    return response
