from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.core.dependencies import CurrentUser, DbSession, require_role
from app.models import User
from app.schemas.auth import UserPublic
from app.schemas.bootstrap import (
    BootstrapConfigureRequest,
    BootstrapInitializeRequest,
    BootstrapInitializeResponse,
    BootstrapStatePublic,
)
from app.services import auth_service, bootstrap_service

router = APIRouter(prefix="/bootstrap", tags=["bootstrap"])

AdminOnly = Annotated[User, Depends(require_role("admin"))]


def _state_response(db: DbSession) -> BootstrapStatePublic:
    return BootstrapStatePublic.model_validate(bootstrap_service.get_bootstrap_state(db))


@router.get("/state", response_model=BootstrapStatePublic)
def get_bootstrap_state(db: DbSession) -> BootstrapStatePublic:
    return _state_response(db)


@router.post("/initialize", response_model=BootstrapInitializeResponse)
def initialize_bootstrap(
    payload: BootstrapInitializeRequest,
    response: Response,
    db: DbSession,
) -> BootstrapInitializeResponse:
    try:
        user = bootstrap_service.initialize_instance(
            db,
            tenant_name=payload.tenant_name,
            admin_email=payload.admin_email,
            admin_password=payload.admin_password,
            notification_from_email=payload.notification_from_email,
            auth_mode=payload.auth_mode,
        )
    except bootstrap_service.BootstrapValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except bootstrap_service.BootstrapConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    recovery_code = auth_service.issue_recovery_code(user)
    db.commit()
    db.refresh(user)
    token = auth_service.create_session_token(user)
    auth_service.set_session_cookie(response, token)
    return BootstrapInitializeResponse(
        access_token=token,
        bootstrap_recovery_code=recovery_code,
        user=UserPublic.model_validate(user),
        state=_state_response(db),
    )


@router.put("/configure", response_model=BootstrapStatePublic)
def configure_bootstrap(
    payload: BootstrapConfigureRequest,
    actor: AdminOnly,
    db: DbSession,
) -> BootstrapStatePublic:
    try:
        state = bootstrap_service.configure_instance(
            db,
            user=actor,
            tenant_name=payload.tenant_name,
            notification_from_email=payload.notification_from_email,
            auth_mode=payload.auth_mode,
        )
    except bootstrap_service.BootstrapValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except bootstrap_service.BootstrapPermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except bootstrap_service.BootstrapConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    db.commit()
    return BootstrapStatePublic.model_validate(state)


@router.post("/complete", response_model=BootstrapStatePublic)
def complete_bootstrap(actor: CurrentUser, db: DbSession) -> BootstrapStatePublic:
    try:
        state = bootstrap_service.complete_bootstrap(db, user=actor)
    except bootstrap_service.BootstrapPermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except (bootstrap_service.BootstrapConflictError, bootstrap_service.BootstrapValidationError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    db.commit()
    return BootstrapStatePublic.model_validate(state)
