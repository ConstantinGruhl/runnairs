"""Tiny SMTP client. Talks to MailHog in compose; same library would
talk to a real SMTP server in production."""
from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

logger = logging.getLogger(__name__)


@dataclass
class SmtpConfig:
    host: str
    port: int
    username: str | None = None
    password: str | None = None
    use_tls: bool = False


def send(*, config: SmtpConfig, sender: str, to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(config.host, config.port, timeout=30) as smtp:
        if config.use_tls:
            smtp.starttls()
        if config.username:
            smtp.login(config.username, config.password or "")
        smtp.send_message(msg)
