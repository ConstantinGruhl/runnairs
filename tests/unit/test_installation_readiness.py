from types import SimpleNamespace

from app.services.installations_service import (
    compute_installation_readiness,
    enabled_modules_for_installation,
)


def test_compute_installation_readiness_reports_missing_items() -> None:
    descriptor = {
        "workspace_connections": ["OPENAI_API_KEY"],
        "user_connections": ["MAILBOX_TOKEN"],
        "modules": [
            {"id": "summary_generation", "required": True, "enabled_by_default": True},
            {"id": "email_delivery", "required": False, "enabled_by_default": True},
        ],
    }
    readiness = compute_installation_readiness(
        descriptor=descriptor,
        available_workspace_connections=set(),
        available_user_connections=set(),
        enabled_modules={"summary_generation"},
    )
    assert readiness.ready is False
    assert readiness.missing_workspace_connections == ["OPENAI_API_KEY"]
    assert readiness.missing_user_connections == ["MAILBOX_TOKEN"]
    assert readiness.disabled_required_modules == []


def test_enabled_modules_for_installation_honors_explicit_empty_list() -> None:
    descriptor = {
        "modules": [
            {"id": "default", "required": True, "enabled_by_default": True},
            {"id": "optional", "required": False, "enabled_by_default": True},
        ]
    }

    assert enabled_modules_for_installation(descriptor, None) == ["default", "optional"]
    assert enabled_modules_for_installation(
        descriptor,
        SimpleNamespace(enabled_modules_json=[]),
    ) == []
