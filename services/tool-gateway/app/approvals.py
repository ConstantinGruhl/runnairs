"""Approval endpoints for the agent SDK.

POST /approvals creates a pending approval row and pauses the run.
POST /approvals/{id}/wait long-polls until the row's status changes
or the chunk timeout elapses; the SDK loops until terminal.
"""
from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from app.auth import RunClaims
from app.db import get_engine

router = APIRouter(prefix="/approvals", tags=["approvals"])

WAIT_CHUNK_SECONDS = 30
WAIT_POLL_INTERVAL_SECONDS = 1


class ApprovalRequest(BaseModel):
    action: str
    title: str
    body: str | None = None
    payload: dict | None = None


@router.post("")
def create_approval(payload: ApprovalRequest, claims: RunClaims) -> dict:
    """Create a pending approval and move the run into awaiting_approval."""
    approval_id = uuid.uuid4()
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO approval
                    (id, run_id, action, title, body, payload_json, status, created_at)
                VALUES
                    (:id, :run_id, :action, :title, :body,
                     CAST(:payload AS jsonb), 'pending', NOW())
                """
            ),
            {
                "id": str(approval_id),
                "run_id": str(claims.run_id),
                "action": payload.action,
                "title": payload.title,
                "body": payload.body,
                "payload": _to_jsonb(payload.payload),
            },
        )
        conn.execute(
            text("UPDATE run SET status = 'awaiting_approval' WHERE id = :id"),
            {"id": str(claims.run_id)},
        )
    return {"approval_id": str(approval_id), "status": "pending"}


@router.post("/{approval_id}/wait")
def wait_for_approval(approval_id: uuid.UUID, claims: RunClaims) -> dict:
    """Long-poll until the approval is decided, or until WAIT_CHUNK_SECONDS."""
    deadline = time.time() + WAIT_CHUNK_SECONDS
    while True:
        row = _fetch(approval_id, claims.run_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "approval not found for this run")

        status_val = row["status"]
        if status_val != "pending":
            # Resume the run on the way out so the next gateway call sees `running`.
            with get_engine().begin() as conn:
                conn.execute(
                    text(
                        "UPDATE run SET status = 'running' WHERE id = :id "
                        "AND status = 'awaiting_approval'"
                    ),
                    {"id": str(claims.run_id)},
                )
            return {
                "status": status_val,
                "decided_by": str(row["decided_by"]) if row["decided_by"] else None,
                "decided_at": row["decided_at"].isoformat() if row["decided_at"] else None,
            }

        if time.time() >= deadline:
            return {"status": "pending"}
        time.sleep(WAIT_POLL_INTERVAL_SECONDS)


def _fetch(approval_id: uuid.UUID, run_id: uuid.UUID) -> dict | None:
    with get_engine().begin() as conn:
        row = conn.execute(
            text(
                "SELECT id, run_id, status, decided_by, decided_at "
                "FROM approval WHERE id = :id AND run_id = :run_id"
            ),
            {"id": str(approval_id), "run_id": str(run_id)},
        ).mappings().first()
    return dict(row) if row else None


def _to_jsonb(value: dict | None) -> str:
    import json
    return json.dumps(value or {})
