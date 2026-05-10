"""Email tool surface.

    >>> from platform_sdk import tools
    >>> tools.email.send(to="alice@example.com", subject="Hi", body="hello")
"""
from __future__ import annotations

from dataclasses import dataclass

from platform_sdk import _client


@dataclass(frozen=True)
class SendResult:
    ok: bool
    backend: str  # "smtp" | "stub"


def send(*, to: str, subject: str, body: str, sender: str | None = None) -> SendResult:
    payload: dict[str, object] = {"to": to, "subject": subject, "body": body}
    if sender is not None:
        payload["sender"] = sender
    res = _client.post("/tools/email/send", payload)
    return SendResult(ok=bool(res.get("ok")), backend=str(res.get("backend", "")))
