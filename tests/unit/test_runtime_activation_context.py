import json

from platform_sdk.context import ctx


def test_ctx_reads_installation_state(monkeypatch) -> None:
    monkeypatch.setenv(
        "RUN_INSTALLATION_STATE",
        json.dumps(
            {
                "enabled_modules": ["summary_generation", "email_delivery"],
                "connections": {
                    "OPENAI_API_KEY": {"provider_key": "openai", "scope": "workspace"},
                    "MAILBOX_TOKEN": {"provider_key": "mailbox", "scope": "user"},
                },
                "config": {"delivery_mode": "email"},
            }
        ),
    )
    assert ctx.module_enabled("email_delivery") is True
    assert ctx.connection("OPENAI_API_KEY")["provider_key"] == "openai"
    assert ctx.installation_config()["delivery_mode"] == "email"
