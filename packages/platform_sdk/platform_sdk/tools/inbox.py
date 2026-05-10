"""tools.inbox.list — fetch emails from the user's connected mailbox."""
from __future__ import annotations

from platform_sdk import _client


def list_emails() -> list[dict]:
    res = _client.post("/tools/inbox/list", {})
    return list(res.get("emails", []))
