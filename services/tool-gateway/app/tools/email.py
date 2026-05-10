"""HTTP surface for tools.email.send.

Resolves the workspace's SMTP creds (if any), checks that the agent's
manifest grants email.send and any pending approval-required gate is
satisfied, and sends via the local MailHog in compose.
"""
from __future__ import annotations

import logging
import time
import uuid
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from app import audit, secrets
from app.auth import RunClaims
from app.config import settings
from app.db import get_engine
from app.policy import ensure_tool_allowed
from app.tools.email_smtp import SmtpConfig, send as smtp_send

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tools/email", tags=["email"])

TOOL_NAME = "email.send"
DEFAULT_SENDER = "agents@platform.local"


class SendRequest(BaseModel):
    to: str
    subject: str
    body: str
    sender: str | None = None


class SendResponse(BaseModel):
    ok: bool
    backend: str  # "smtp" | "stub"


@router.post("/send", response_model=SendResponse)
def send(payload: SendRequest, claims: RunClaims) -> SendResponse:
    ensure_tool_allowed(claims, TOOL_NAME)

    if TOOL_NAME in claims.approvals_required_for:
        if not _has_recent_approval(claims.run_id, TOOL_NAME):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"{TOOL_NAME!r} requires approval; call ctx.request_approval first",
            )

    sender = payload.sender or DEFAULT_SENDER
    config = SmtpConfig(host=settings.mailhog_host, port=settings.mailhog_port)

    # Optional workspace overrides.
    try:
        host = secrets.resolve(claims, "SMTP_HOST")
        config = SmtpConfig(host=host, port=int(secrets.resolve(claims, "SMTP_PORT") or "1025"))
    except secrets.SecretResolutionError:
        pass
    try:
        config.username = secrets.resolve(claims, "SMTP_USERNAME")
        config.password = secrets.resolve(claims, "SMTP_PASSWORD")
    except secrets.SecretResolutionError:
        pass

    start = time.perf_counter()
    error: Exception | None = None
    try:
        smtp_send(
            config=config,
            sender=sender,
            to=str(payload.to),
            subject=payload.subject,
            body=payload.body,
        )
    except Exception as e:  # noqa: BLE001
        error = e

    duration_ms = int((time.perf_counter() - start) * 1000)
    audit_args = {
        "to": str(payload.to),
        "subject": payload.subject,
        "body_preview": payload.body[:200],
        "sender": sender,
    }
    if error is not None:
        audit.write(
            claims=claims,
            tool_name=TOOL_NAME,
            args=audit_args,
            result_summary=None,
            status="error",
            duration_ms=duration_ms,
            cost_usd=Decimal("0"),
        )
        logger.exception("email.send failed", exc_info=error)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"email failed: {error}")

    audit.write(
        claims=claims,
        tool_name=TOOL_NAME,
        args=audit_args,
        result_summary=f"sent to {payload.to}",
        status="ok",
        duration_ms=duration_ms,
        cost_usd=Decimal("0"),
    )
    return SendResponse(ok=True, backend="smtp")


def _has_recent_approval(run_id: uuid.UUID, action: str) -> bool:
    with get_engine().begin() as conn:
        row = conn.execute(
            text(
                "SELECT id FROM approval "
                "WHERE run_id = :run_id AND action = :action "
                "  AND status = 'approved' "
                "ORDER BY decided_at DESC LIMIT 1"
            ),
            {"run_id": str(run_id), "action": action},
        ).first()
    return row is not None
