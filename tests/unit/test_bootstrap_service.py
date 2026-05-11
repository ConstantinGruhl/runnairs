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
    assert state["supported_auth_modes"] == ["built_in", "hybrid", "oidc"]
    assert state["built_in_login_enabled"] is True
    assert state["oidc_provider_state"] == {"exists": False, "is_enabled": False, "name": None}
    assert "bootstrap admin has not been created" in state["blocking_reasons"]
    assert "authentication mode has not been selected" in state["blocking_reasons"]
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
    assert state["auth_mode"] == "built_in"
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
    assert state["operator_guidance"] == []


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

    assert "authentication mode has not been selected" in str(exc.value)
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
            "auth_mode": "built_in",
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
            "auth_mode": "built_in",
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


def test_operator_guidance_includes_runtime_fix_steps() -> None:
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
            "database_ok": False,
        },
    )

    assert {item["key"] for item in state["operator_guidance"]} == {
        "platform_secrets_key_configured",
        "database_ok",
    }
    assert any("PLATFORM_SECRETS_KEY" in item["action"] for item in state["operator_guidance"])


def test_validate_auth_mode_accepts_built_in() -> None:
    assert bootstrap_service.validate_auth_mode("built_in") == "built_in"


def test_validate_auth_mode_accepts_hybrid_and_oidc() -> None:
    assert bootstrap_service.validate_auth_mode("hybrid") == "hybrid"
    assert bootstrap_service.validate_auth_mode("oidc") == "oidc"


def test_validate_auth_mode_rejects_unsupported_values() -> None:
    with pytest.raises(bootstrap_service.BootstrapValidationError, match="unsupported auth_mode"):
        bootstrap_service.validate_auth_mode("saml")


def test_validate_auth_mode_for_state_requires_enabled_provider_for_oidc() -> None:
    with pytest.raises(bootstrap_service.BootstrapValidationError, match="requires an enabled OIDC provider"):
        bootstrap_service.validate_auth_mode_for_state(
            "oidc",
            provider_state={"exists": True, "is_enabled": False, "name": "Okta"},
        )

    with pytest.raises(bootstrap_service.BootstrapValidationError, match="requires an enabled OIDC provider"):
        bootstrap_service.validate_auth_mode_for_state(
            "hybrid",
            provider_state={"exists": False, "is_enabled": False, "name": None},
        )


def test_validate_auth_mode_for_state_allows_built_in_without_provider() -> None:
    assert (
        bootstrap_service.validate_auth_mode_for_state(
            "built_in",
            provider_state={"exists": False, "is_enabled": False, "name": None},
        )
        == "built_in"
    )


def test_validate_auth_mode_for_state_allows_oidc_when_provider_enabled() -> None:
    assert (
        bootstrap_service.validate_auth_mode_for_state(
            "oidc",
            provider_state={"exists": True, "is_enabled": True, "name": "Okta"},
        )
        == "oidc"
    )


def test_built_in_login_disabled_when_auth_mode_is_oidc() -> None:
    state = bootstrap_service.summarize_bootstrap(
        stored={
            "tenant_id": "tenant-1",
            "tenant_name": "Demo Workspace",
            "admin_user_id": "user-1",
            "admin_email": "admin@example.com",
            "notification_from_email": "ops@example.com",
            "auth_mode": "oidc",
            "completed_at": None,
        },
        checks={
            "jwt_secret_valid": True,
            "platform_secrets_key_configured": True,
            "database_ok": True,
        },
        provider_state={"exists": True, "is_enabled": True, "name": "Okta"},
    )

    assert state["built_in_login_enabled"] is False
    assert state["oidc_provider_state"] == {"exists": True, "is_enabled": True, "name": "Okta"}
