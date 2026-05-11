from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from app import main as main_module
from app.core import db as db_module
from app.core.config import settings
from app.models import Base


def _postgres_url(database: str) -> URL:
    return URL.create(
        "postgresql+psycopg",
        username=os.getenv("POSTGRES_USER", "platform"),
        password=os.getenv("POSTGRES_PASSWORD", "platform"),
        host=os.getenv("BOOTSTRAP_TEST_DB_HOST", "127.0.0.1"),
        port=int(os.getenv("BOOTSTRAP_TEST_DB_PORT", "5432")),
        database=database,
    )


@pytest.fixture
def bootstrap_admin_payload() -> dict[str, str]:
    return {
        "tenant_name": "Bootstrap Workspace",
        "admin_email": "bootstrap-admin@example.com",
        "admin_password": "bootstrap-pass-123",
        "notification_from_email": "ops@example.com",
        "auth_mode": "built_in",
    }


@pytest.fixture
def bootstrap_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    db_name = f"bootstrap_test_{uuid.uuid4().hex}"
    admin_engine = create_engine(
        _postgres_url("postgres"),
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
        future=True,
    )

    try:
        with admin_engine.connect() as conn:
            conn.execute(text(f"CREATE DATABASE {db_name}"))
    except Exception as exc:
        admin_engine.dispose()
        pytest.skip(f"bootstrap integration tests require local postgres on 127.0.0.1:5432: {exc}")

    engine = create_engine(_postgres_url(db_name), pool_pre_ping=True, future=True)
    Base.metadata.create_all(engine)
    testing_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "jwt_secret", "x" * 32)
    monkeypatch.setattr(settings, "platform_secrets_key", "")
    monkeypatch.setattr(settings, "database_url", str(_postgres_url(db_name)))
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", testing_session_local)
    monkeypatch.setattr(main_module, "SessionLocal", testing_session_local)

    try:
        with TestClient(main_module.app) as client:
            yield client
    finally:
        engine.dispose()
        with admin_engine.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": db_name},
            )
            conn.execute(text(f"DROP DATABASE IF EXISTS {db_name}"))
        admin_engine.dispose()


def test_fresh_instance_returns_bootstrap_required_state(
    bootstrap_client: TestClient,
) -> None:
    response = bootstrap_client.get("/bootstrap/state")

    assert response.status_code == 200
    payload = response.json()
    assert payload["bootstrap_required"] is True
    assert payload["completed"] is False
    assert payload["admin_created"] is False
    assert payload["supported_auth_modes"] == ["built_in", "hybrid", "oidc"]
    assert payload["built_in_login_enabled"] is True
    assert payload["oidc_provider_state"] == {"exists": False, "is_enabled": False, "name": None}
    assert payload["checks"]["database_ok"] is True
    assert "bootstrap admin has not been created" in payload["blocking_reasons"]
    assert any(
        item["key"] == "platform_secrets_key_configured"
        and "PLATFORM_SECRETS_KEY" in item["action"]
        for item in payload["operator_guidance"]
    )


def test_anonymous_second_bootstrap_initialization_is_rejected(
    bootstrap_client: TestClient,
    bootstrap_admin_payload: dict[str, str],
) -> None:
    first_response = bootstrap_client.post("/bootstrap/initialize", json=bootstrap_admin_payload)
    second_response = bootstrap_client.post("/bootstrap/initialize", json=bootstrap_admin_payload)

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == "bootstrap admin already exists; sign in to resume setup"


def test_bootstrap_admin_can_log_back_in_and_resume_partial_setup(
    bootstrap_client: TestClient,
    bootstrap_admin_payload: dict[str, str],
) -> None:
    initialize_response = bootstrap_client.post("/bootstrap/initialize", json=bootstrap_admin_payload)
    assert initialize_response.status_code == 200

    login_response = bootstrap_client.post(
        "/auth/login",
        json={
            "email": bootstrap_admin_payload["admin_email"],
            "password": bootstrap_admin_payload["admin_password"],
        },
    )
    assert login_response.status_code == 200

    token = login_response.json()["access_token"]
    configure_response = bootstrap_client.put(
        "/bootstrap/configure",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "tenant_name": "Renamed Workspace",
            "notification_from_email": "alerts@example.com",
        },
    )

    assert configure_response.status_code == 200
    payload = configure_response.json()
    assert payload["bootstrap_required"] is True
    assert payload["completed"] is False
    assert payload["admin_created"] is True
    assert payload["tenant_name"] == "Renamed Workspace"
    assert payload["notification_from_email"] == "alerts@example.com"
    assert payload["instance_admin_email"] == bootstrap_admin_payload["admin_email"]
