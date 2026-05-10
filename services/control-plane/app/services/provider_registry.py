from __future__ import annotations

PROVIDER_PLUGINS = {
    "openai": {"scope": "workspace", "connection_keys": ["OPENAI_API_KEY"]},
    "smtp_email": {
        "scope": "workspace",
        "connection_keys": ["SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD"],
    },
    "mailbox": {"scope": "user", "connection_keys": ["MAILBOX_TOKEN"]},
}
