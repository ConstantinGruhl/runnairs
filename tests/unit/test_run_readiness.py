import pytest

from app.services.installations_service import InstallationNotReadyError, ensure_installation_ready


def test_ensure_installation_ready_reports_all_blockers() -> None:
    summary = {
        "missing_workspace_connections": ["OPENAI_API_KEY"],
        "missing_user_connections": ["MAILBOX_TOKEN"],
        "disabled_required_modules": ["default"],
    }

    with pytest.raises(InstallationNotReadyError) as exc:
        ensure_installation_ready(summary, trigger_label="manual run")

    message = str(exc.value)
    assert "missing workspace connections: OPENAI_API_KEY" in message
    assert "missing user connections: MAILBOX_TOKEN" in message
    assert "disabled required modules: default" in message


def test_ensure_installation_ready_allows_ready_summary() -> None:
    summary = {
        "missing_workspace_connections": [],
        "missing_user_connections": [],
        "disabled_required_modules": [],
    }

    ensure_installation_ready(summary, trigger_label="scheduled run")
