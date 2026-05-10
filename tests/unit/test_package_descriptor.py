from pathlib import Path

from app.services.package_descriptor import load_package_descriptor, normalize_stored_descriptor


def test_load_package_descriptor_prefers_automation_yaml(tmp_path: Path) -> None:
    (tmp_path / "automation.yaml").write_text(
        "name: weekly-summary\n"
        "display_name: Weekly Summary\n"
        "entrypoint: main:run\n"
        "modules:\n"
        "  - id: email_delivery\n"
        "    required: true\n",
        encoding="utf-8",
    )
    descriptor = load_package_descriptor(tmp_path)
    assert descriptor.format == "automation"
    assert descriptor.data["modules"][0]["id"] == "email_delivery"


def test_load_package_descriptor_normalizes_agent_yaml(tmp_path: Path) -> None:
    (tmp_path / "agent.yaml").write_text(
        "name: hello-world\n"
        "display_name: Hello World\n"
        "entrypoint: main:run\n"
        "permissions:\n"
        "  tools:\n"
        "    - llm.complete\n",
        encoding="utf-8",
    )
    descriptor = load_package_descriptor(tmp_path)
    assert descriptor.format == "legacy_agent"
    assert descriptor.data["modules"][0]["id"] == "default"
    assert descriptor.data["tools"] == ["llm.complete"]


def test_normalize_stored_descriptor_handles_legacy_rows() -> None:
    normalized = normalize_stored_descriptor(
        {
            "name": "inbox-triage",
            "display_name": "Inbox Triage",
            "entrypoint": "main:run",
            "permissions": {
                "tools": ["llm.complete"],
                "secrets": [
                    {"name": "OPENAI_API_KEY", "scope": "workspace"},
                    {"name": "MAILBOX_TOKEN", "scope": "user"},
                ],
            },
        },
        descriptor_format="legacy_agent",
    )

    assert normalized["modules"] == [
        {
            "id": "default",
            "title": "Inbox Triage",
            "required": True,
            "enabled_by_default": True,
        }
    ]
    assert normalized["tools"] == ["llm.complete"]
    assert normalized["workspace_connections"] == ["OPENAI_API_KEY"]
    assert normalized["user_connections"] == ["MAILBOX_TOKEN"]
