"""tools.inbox.list — mock IMAP-like inbox.

Requires the triggering user's MAILBOX_TOKEN (user-scope) so the agent
can demonstrate that user-scope secrets gate access correctly. The
returned emails are static for the prototype.
"""
from __future__ import annotations

import logging
import time
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app import audit, secrets
from app.auth import RunClaims
from app.policy import ensure_tool_allowed

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tools/inbox", tags=["inbox"])

TOOL_NAME = "inbox.list"


class InboxResponse(BaseModel):
    emails: list[dict]


_FAKE_EMAILS: list[dict] = [
    {
        "from": "alice@bigco.com",
        "subject": "Quick question on your renewal proposal",
        "body": "Hi — your account team mentioned an upcoming renewal. "
                "Can we set up a 30-min call to walk through pricing? Best, Alice",
        "received_at": "2026-05-09T08:14:00Z",
    },
    {
        "from": "noreply@billing.example.com",
        "subject": "Your invoice INV-2026-04 is ready",
        "body": "Your monthly invoice is attached. No action needed.",
        "received_at": "2026-05-09T03:00:00Z",
    },
    {
        "from": "marcus@vendor.io",
        "subject": "RE: integration plans",
        "body": "Following up on last week's call — we have the API spec drafted. "
                "Can you confirm whether OAuth2 is acceptable for service auth?",
        "received_at": "2026-05-08T16:42:00Z",
    },
    {
        "from": "team-news@company.local",
        "subject": "Weekly newsletter — May 9",
        "body": "Highlights this week: launched new dashboard, hired two engineers. "
                "Full details in the wiki.",
        "received_at": "2026-05-09T09:00:00Z",
    },
    {
        "from": "support@important-customer.com",
        "subject": "URGENT: webhook delivery failing for 4 hours",
        "body": "We've been unable to receive webhooks since 04:30 UTC. Our "
                "integration is broken in production — please investigate.",
        "received_at": "2026-05-09T08:35:00Z",
    },
]


@router.post("/list", response_model=InboxResponse)
def list_emails(claims: RunClaims) -> InboxResponse:
    ensure_tool_allowed(claims, TOOL_NAME)

    start = time.perf_counter()
    try:
        # Resolution proves the user has connected their mailbox.
        token = secrets.resolve(claims, "MAILBOX_TOKEN")
    except secrets.SecretResolutionError as e:
        audit.write(
            claims=claims,
            tool_name=TOOL_NAME,
            args={},
            result_summary=f"missing MAILBOX_TOKEN: {e}",
            status="error",
            duration_ms=int((time.perf_counter() - start) * 1000),
            cost_usd=Decimal("0"),
        )
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "MAILBOX_TOKEN is not connected for the triggering user; "
            "they need to connect their account from the catalog page.",
        ) from e

    audit.write(
        claims=claims,
        tool_name=TOOL_NAME,
        args={"mailbox_token_len": len(token)},
        result_summary=f"{len(_FAKE_EMAILS)} emails",
        status="ok",
        duration_ms=int((time.perf_counter() - start) * 1000),
        cost_usd=Decimal("0"),
        secret_values=[token],
    )
    return InboxResponse(emails=list(_FAKE_EMAILS))
