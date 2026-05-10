from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.core.dependencies import CurrentUser, DbSession, require_role
from app.models import Agent, Approval, ApprovalStatus, Run, RunStatus, User

router = APIRouter(tags=["approvals"])

AdminOnly = Annotated[User, Depends(require_role("admin"))]


class ApprovalPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    action: str
    title: str | None
    body: str | None
    payload_json: dict | None
    status: str
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    created_at: datetime


class DecisionRequest(BaseModel):
    decision: Literal["approved", "denied"]


@router.get("/runs/{run_id}/approvals", response_model=list[ApprovalPublic])
def list_approvals_for_run(
    run_id: uuid.UUID,
    actor: CurrentUser,
    db: DbSession,
) -> list[ApprovalPublic]:
    """List approvals for a run. Visible to the triggering user + admins."""
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    agent = db.get(Agent, run.agent_id)
    if agent is None or agent.tenant_id != actor.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    if actor.role.value != "admin" and run.triggering_user_id != actor.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your run")

    rows = (
        db.execute(
            select(Approval).where(Approval.run_id == run_id).order_by(Approval.created_at)
        )
        .scalars()
        .all()
    )
    return [
        ApprovalPublic.model_validate(
            {
                "id": a.id,
                "run_id": a.run_id,
                "action": a.action,
                "title": a.title,
                "body": a.body,
                "payload_json": a.payload_json,
                "status": a.status.value,
                "decided_by": a.decided_by,
                "decided_at": a.decided_at,
                "created_at": a.created_at,
            }
        )
        for a in rows
    ]


@router.post("/admin/approvals/{approval_id}/decide", response_model=ApprovalPublic)
def decide_approval(
    approval_id: uuid.UUID,
    payload: DecisionRequest,
    actor: AdminOnly,
    db: DbSession,
) -> ApprovalPublic:
    approval = db.get(Approval, approval_id)
    if approval is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "approval not found")

    run = db.get(Run, approval.run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    agent = db.get(Agent, run.agent_id)
    if agent is None or agent.tenant_id != actor.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "approval not found")

    if approval.status != ApprovalStatus.pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "approval already decided")

    approval.status = ApprovalStatus(payload.decision)
    approval.decided_by = actor.id
    approval.decided_at = datetime.now(timezone.utc)
    # Run.status will be set back to running by the gateway long-poll once
    # it sees the decision; nudge it here too in case the wait already timed out.
    if run.status == RunStatus.awaiting_approval:
        run.status = RunStatus.running
    db.commit()
    db.refresh(approval)

    return ApprovalPublic.model_validate(
        {
            "id": approval.id,
            "run_id": approval.run_id,
            "action": approval.action,
            "title": approval.title,
            "body": approval.body,
            "payload_json": approval.payload_json,
            "status": approval.status.value,
            "decided_by": approval.decided_by,
            "decided_at": approval.decided_at,
            "created_at": approval.created_at,
        }
    )
