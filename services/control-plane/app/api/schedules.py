from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.core.dependencies import DbSession, require_role
from app.models import Agent, Schedule, User

router = APIRouter(tags=["schedules"])

DevOrAdmin = Annotated[User, Depends(require_role("developer", "admin"))]


class SchedulePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    cron: str
    timezone: str
    enabled: bool
    inputs_json: dict[str, Any] | None
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime


class ScheduleCreate(BaseModel):
    cron: str
    timezone: str = "UTC"
    enabled: bool = True
    inputs: dict[str, Any] | None = None


class ScheduleUpdate(BaseModel):
    cron: str | None = None
    timezone: str | None = None
    enabled: bool | None = None
    inputs: dict[str, Any] | None = None


def _validate_cron(expr: str) -> None:
    if not croniter.is_valid(expr):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"invalid cron expression: {expr!r}")


def _next_at(cron: str, base: datetime) -> datetime:
    return croniter(cron, base).get_next(datetime)


def _to_public(s: Schedule) -> SchedulePublic:
    return SchedulePublic.model_validate(
        {
            "id": s.id,
            "agent_id": s.agent_id,
            "cron": s.cron,
            "timezone": s.timezone,
            "enabled": s.enabled,
            "inputs_json": s.inputs_json,
            "last_run_at": s.last_run_at,
            "next_run_at": s.next_run_at,
            "created_at": s.created_at,
        }
    )


def _agent_or_404(db, actor: User, slug: str) -> Agent:
    agent = db.execute(
        select(Agent).where(Agent.tenant_id == actor.tenant_id, Agent.slug == slug)
    ).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "agent not found")
    return agent


@router.get("/dev/agents/{slug}/schedules", response_model=list[SchedulePublic])
def list_schedules(slug: str, actor: DevOrAdmin, db: DbSession) -> list[SchedulePublic]:
    agent = _agent_or_404(db, actor, slug)
    rows = (
        db.execute(
            select(Schedule).where(Schedule.agent_id == agent.id).order_by(Schedule.created_at)
        )
        .scalars()
        .all()
    )
    return [_to_public(s) for s in rows]


@router.post(
    "/dev/agents/{slug}/schedules",
    response_model=SchedulePublic,
    status_code=status.HTTP_201_CREATED,
)
def create_schedule(
    slug: str,
    payload: ScheduleCreate,
    actor: DevOrAdmin,
    db: DbSession,
) -> SchedulePublic:
    agent = _agent_or_404(db, actor, slug)
    _validate_cron(payload.cron)
    schedule = Schedule(
        agent_id=agent.id,
        cron=payload.cron,
        timezone=payload.timezone,
        enabled=payload.enabled,
        inputs_json=payload.inputs,
        next_run_at=_next_at(payload.cron, datetime.now(tz=__import__("datetime").timezone.utc)),
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return _to_public(schedule)


@router.patch("/dev/schedules/{schedule_id}", response_model=SchedulePublic)
def update_schedule(
    schedule_id: uuid.UUID,
    payload: ScheduleUpdate,
    actor: DevOrAdmin,
    db: DbSession,
) -> SchedulePublic:
    schedule = db.get(Schedule, schedule_id)
    if schedule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "schedule not found")
    agent = db.get(Agent, schedule.agent_id)
    if agent is None or agent.tenant_id != actor.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "schedule not found")

    if payload.cron is not None:
        _validate_cron(payload.cron)
        schedule.cron = payload.cron
        schedule.next_run_at = _next_at(
            payload.cron, datetime.now(tz=__import__("datetime").timezone.utc)
        )
    if payload.timezone is not None:
        schedule.timezone = payload.timezone
    if payload.enabled is not None:
        schedule.enabled = payload.enabled
    if payload.inputs is not None:
        schedule.inputs_json = payload.inputs

    db.commit()
    db.refresh(schedule)
    return _to_public(schedule)


@router.delete("/dev/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(schedule_id: uuid.UUID, actor: DevOrAdmin, db: DbSession) -> None:
    schedule = db.get(Schedule, schedule_id)
    if schedule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "schedule not found")
    agent = db.get(Agent, schedule.agent_id)
    if agent is None or agent.tenant_id != actor.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "schedule not found")
    db.delete(schedule)
    db.commit()
