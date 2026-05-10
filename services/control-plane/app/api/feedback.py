from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.core.dependencies import CurrentUser, DbSession, require_role
from app.models import Agent, Feedback, FeedbackRating, Run, User

router = APIRouter(tags=["feedback"])

DevOrAdmin = Annotated[User, Depends(require_role("developer", "admin"))]


class FeedbackCreate(BaseModel):
    rating: Literal["up", "down"]
    comment: str | None = None


class FeedbackPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    user_id: uuid.UUID
    rating: str
    comment: str | None
    created_at: datetime


class AgentFeedbackEntry(BaseModel):
    feedback_id: uuid.UUID
    run_id: uuid.UUID
    rating: str
    comment: str | None
    created_at: datetime
    user_id: uuid.UUID


class AgentFeedbackSummary(BaseModel):
    agent_slug: str
    up_count: int
    down_count: int
    total_runs_with_feedback: int
    items: list[AgentFeedbackEntry]


def _to_public(f: Feedback) -> FeedbackPublic:
    return FeedbackPublic.model_validate(
        {
            "id": f.id,
            "run_id": f.run_id,
            "user_id": f.user_id,
            "rating": f.rating.value,
            "comment": f.comment,
            "created_at": f.created_at,
        }
    )


def _resolve_run(db, actor: User, run_id: uuid.UUID) -> Run:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    agent = db.get(Agent, run.agent_id)
    if agent is None or agent.tenant_id != actor.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    return run


@router.post("/runs/{run_id}/feedback", response_model=FeedbackPublic, status_code=status.HTTP_201_CREATED)
def leave_feedback(
    run_id: uuid.UUID,
    payload: FeedbackCreate,
    actor: CurrentUser,
    db: DbSession,
) -> FeedbackPublic:
    run = _resolve_run(db, actor, run_id)
    if actor.role.value != "admin" and run.triggering_user_id != actor.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "you can only leave feedback on your own runs")

    existing = db.execute(
        select(Feedback).where(Feedback.run_id == run_id, Feedback.user_id == actor.id)
    ).scalar_one_or_none()
    if existing is not None:
        existing.rating = FeedbackRating(payload.rating)
        existing.comment = payload.comment
        db.commit()
        db.refresh(existing)
        return _to_public(existing)

    fb = Feedback(
        run_id=run_id,
        user_id=actor.id,
        rating=FeedbackRating(payload.rating),
        comment=payload.comment,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return _to_public(fb)


@router.get("/runs/{run_id}/feedback", response_model=FeedbackPublic | None)
def get_my_feedback(
    run_id: uuid.UUID, actor: CurrentUser, db: DbSession
) -> FeedbackPublic | None:
    _resolve_run(db, actor, run_id)
    fb = db.execute(
        select(Feedback).where(Feedback.run_id == run_id, Feedback.user_id == actor.id)
    ).scalar_one_or_none()
    return _to_public(fb) if fb else None


@router.get("/dev/agents/{slug}/feedback", response_model=AgentFeedbackSummary)
def agent_feedback(
    slug: str, actor: DevOrAdmin, db: DbSession
) -> AgentFeedbackSummary:
    agent = db.execute(
        select(Agent).where(Agent.tenant_id == actor.tenant_id, Agent.slug == slug)
    ).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "agent not found")

    rows = db.execute(
        select(Feedback)
        .join(Run, Run.id == Feedback.run_id)
        .where(Run.agent_id == agent.id)
        .order_by(Feedback.created_at.desc())
    ).scalars().all()

    up = sum(1 for r in rows if r.rating == FeedbackRating.up)
    down = sum(1 for r in rows if r.rating == FeedbackRating.down)
    return AgentFeedbackSummary(
        agent_slug=agent.slug,
        up_count=up,
        down_count=down,
        total_runs_with_feedback=len({r.run_id for r in rows}),
        items=[
            AgentFeedbackEntry(
                feedback_id=r.id,
                run_id=r.run_id,
                rating=r.rating.value,
                comment=r.comment,
                created_at=r.created_at,
                user_id=r.user_id,
            )
            for r in rows
        ],
    )
