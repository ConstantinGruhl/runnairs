"""tools.inbox.list — fetch emails from the user's connected mailbox."""
from __future__ import annotations

from platform_sdk._client import post


def list_emails() -> list[dict]:
    res = post("/tools/inbox/list", {})
    return list(res.get("emails", []))
