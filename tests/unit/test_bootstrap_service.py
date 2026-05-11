from __future__ import annotations

import pytest

from app.services import bootstrap_service


def test_summarize_bootstrap_reports_fresh_instance() -> None:
    state = bootstrap_service.summarize_bootstrap(
        stored=None,
        checks={
            "jwt_secret_valid": False,
            "platform_secrets_key_configured": False,
            "database_ok": True,
        },
    )

    assert state["bootstrap_required"] is True
    assert state["admin_created"] is False
    assert "bootstrap admin has not been created" in state["blocking_reasons"]
    assert state["ready_for_completion"] is False


def test_summarize_bootstrap_reports_resumable_partial_state() -> None:
    state = bootstrap_service.summarize_bootstrap(
        stored={
            "tenant_id": "tenant-1",
            "tenant_name": "Demo Workspace",
            "admin_user_id": "user-1",
            "admin_email": "admin@example.com",
            "notification_from_email": "ops@example.com",
            "auth_mode": "built_in",
            "completed_at": None,
        },
        checks={
            "jwt_secret_valid": True,
            "platform_secrets_key_configured": False,
            "database_ok": True,
        },
    )

    assert state["bootstrap_required"] is True
    assert state["admin_created"] is True
    assert state["instance_admin_email"] == "admin@example.com"
    assert state["blocking_reasons"] == ["PLATFORM_SECRETS_KEY is not configured"]


def test_validate_completion_state_accepts_ready_state() -> None:
    state = bootstrap_service.summarize_bootstrap(
        stored={
            "tenant_id": "tenant-1",
            "tenant_name": "Demo Workspace",
            "admin_user_id": "user-1",
            "admin_email": "admin@example.com",
            "notification_from_email": "ops@example.com",
            "auth_mode": "built_in",
            "completed_at": None,
        },
        checks={
            "jwt_secret_valid": True,
            "platform_secrets_key_configured": True,
            "database_ok": True,
        },
    )

    bootstrap_service.validate_completion_state(state)
    assert state["ready_for_completion"] is True


def test_validate_completion_state_rejects_missing_requirements() -> None:
    state = bootstrap_service.summarize_bootstrap(
        stored={
            "tenant_id": "tenant-1",
            "tenant_name": "Demo Workspace",
            "admin_user_id": "user-1",
            "admin_email": "admin@example.com",
            "completed_at": None,
        },
        checks={
            "jwt_secret_valid": True,
            "platform_secrets_key_configured": True,
            "database_ok": False,
        },
    )

    with pytest.raises(bootstrap_service.BootstrapValidationError) as exc:
        bootstrap_service.validate_completion_state(state)

    assert "notification from email is missing" in str(exc.value)
    assert "database connectivity check failed" in str(exc.value)


def test_only_bootstrap_admin_may_continue_setup() -> None:
    state = bootstrap_service.summarize_bootstrap(
        stored={
            "tenant_id": "tenant-1",
            "tenant_name": "Demo Workspace",
            "admin_user_id": "user-1",
            "admin_email": "admin@example.com",
            "notification_from_email": "ops@example.com",
            "completed_at": None,
        },
        checks={
            "jwt_secret_valid": True,
            "platform_secrets_key_configured": True,
            "database_ok": True,
        },
    )

    with pytest.raises(bootstrap_service.BootstrapPermissionError):
        bootstrap_service.ensure_bootstrap_admin(
            state,
            user_id="user-2",
            role="admin",
        )


def test_only_bootstrap_admin_may_log_in_during_bootstrap() -> None:
    state = bootstrap_service.summarize_bootstrap(
        stored={
            "tenant_id": "tenant-1",
            "tenant_name": "Demo Workspace",
            "admin_user_id": "user-1",
            "admin_email": "admin@example.com",
            "notification_from_email": "ops@example.com",
            "completed_at": None,
        },
        checks={
            "jwt_secret_valid": True,
            "platform_secrets_key_configured": True,
            "database_ok": True,
        },
    )

    bootstrap_service.ensure_login_allowed(state, user_id="user-1", role="admin")

    with pytest.raises(bootstrap_service.BootstrapPermissionError):
        bootstrap_service.ensure_login_allowed(state, user_id="user-2", role="developer")
