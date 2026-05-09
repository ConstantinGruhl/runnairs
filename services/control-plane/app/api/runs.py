from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.config import settings
from app.core.dependencies import CurrentUser, DbSession
from app.execution.job_queue import RqJobQueue
from app.models import Agent, AgentStatus, Run, RunStatus, RunTrigger
from app.schemas.runs import RunPublic, RunStartRequest

router = APIRouter(prefix="/runs", tags=["runs"])


def _to_public(run: Run, agent: Agent | None = None) -> RunPublic:
    return RunPublic.model_validate(
        {
            "id": run.id,
            "agent_id": run.agent_id,
            "agent_version_id": run.agent_version_id,
            "triggering_user_id": run.triggering_user_id,
            "trigger": run.trigger.value,
            "status": run.status.value,
            "inputs_json": run.inputs_json,
            "result_json": run.result_json,
            "error": run.error,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
        }
    )


@router.post("", response_model=RunPublic, status_code=status.HTTP_201_CREATED)
def start_run(payload: RunStartRequest, actor: CurrentUser, db: DbSession) -> RunPublic:
    agent = db.execute(
        select(Agent).where(
            Agent.tenant_id == actor.tenant_id,
            Agent.slug == payload.agent_slug,
        )
    ).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "agent not found")

    # End users may only run approved agents; admins/devs may run drafts too.
    if agent.status != AgentStatus.approved and actor.role.value == "user":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "agent is not approved for end-user runs",
        )
    if agent.current_version_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "agent has no current version; deploy one first",
        )

    run = Run(
        agent_id=agent.id,
        agent_version_id=agent.current_version_id,
        triggering_user_id=actor.id,
        trigger=RunTrigger.manual,
        status=RunStatus.queued,
        inputs_json=payload.inputs or {},
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    queue = RqJobQueue(settings.redis_url)
    queue.enqueue(run.id)

    return _to_public(run)


@router.get("/{run_id}", response_model=RunPublic)
def get_run(run_id: uuid.UUID, actor: CurrentUser, db: DbSession) -> RunPublic:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    agent = db.get(Agent, run.agent_id)
    if agent is None or agent.tenant_id != actor.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    return _to_public(run, agent)
