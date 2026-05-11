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
def built_in_iam_payload() -> dict[str, str]:
    return {
        "tenant_name": "Built-In IAM Workspace",
        "admin_email": "bootstrap-admin@example.com",
        "admin_password": "bootstrap-pass-123",
        "notification_from_email": "ops@example.com",
        "auth_mode": "built_in",
    }


@pytest.fixture
def built_in_iam_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    db_name = f"auth_test_{uuid.uuid4().hex}"
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
        pytest.skip(f"auth integration tests require local postgres on 127.0.0.1:5432: {exc}")

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
    monkeypatch.setattr(settings, "platform_secrets_key", "integration-secret-key")
    monkeypatch.setattr(settings, "database_url", str(_postgres_url(db_name)))
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", testing_session_local)
    monkeypatch.setattr(main_module, "SessionLocal", testing_session_local)

    try:
        with TestClient(main_module.app, base_url="https://testserver") as client:
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


def _complete_bootstrap(client: TestClient, payload: dict[str, str]) -> dict:
    initialize_response = client.post("/bootstrap/initialize", json=payload)
    assert initialize_response.status_code == 200

    token = initialize_response.json()["access_token"]
    complete_response = client.post(
        "/bootstrap/complete",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert complete_response.status_code == 200
    return initialize_response.json()


def test_login_sets_session_cookie_and_me_accepts_cookie(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
) -> None:
    _complete_bootstrap(built_in_iam_client, built_in_iam_payload)
    built_in_iam_client.post("/auth/logout")

    login_response = built_in_iam_client.post(
        "/auth/login",
        json={
            "email": built_in_iam_payload["admin_email"],
            "password": built_in_iam_payload["admin_password"],
        },
    )

    assert login_response.status_code == 200
    assert "platform_session=" in login_response.headers["set-cookie"]

    me_response = built_in_iam_client.get("/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["email"] == built_in_iam_payload["admin_email"]


def test_logout_clears_cookie_session(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
) -> None:
    _complete_bootstrap(built_in_iam_client, built_in_iam_payload)

    logout_response = built_in_iam_client.post("/auth/logout")

    assert logout_response.status_code == 204
    assert "platform_session=" in logout_response.headers["set-cookie"]

    me_response = built_in_iam_client.get("/auth/me")
    assert me_response.status_code == 401


def test_recovery_completion_invalidates_old_session_tokens(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
) -> None:
    initialize_payload = _complete_bootstrap(built_in_iam_client, built_in_iam_payload)
    recovery_code = initialize_payload["bootstrap_recovery_code"]

    login_response = built_in_iam_client.post(
        "/auth/login",
        json={
            "email": built_in_iam_payload["admin_email"],
            "password": built_in_iam_payload["admin_password"],
        },
    )
    assert login_response.status_code == 200
    old_token = login_response.json()["access_token"]

    recovery_response = built_in_iam_client.post(
        "/auth/recovery/complete",
        json={
            "email": built_in_iam_payload["admin_email"],
            "recovery_code": recovery_code,
            "new_password": "Recoveredpass456",
        },
    )

    assert recovery_response.status_code == 200

    old_session_response = built_in_iam_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {old_token}"},
    )
    assert old_session_response.status_code == 401

    failed_old_login = built_in_iam_client.post(
        "/auth/login",
        json={
            "email": built_in_iam_payload["admin_email"],
            "password": built_in_iam_payload["admin_password"],
        },
    )
    assert failed_old_login.status_code == 401

    new_login = built_in_iam_client.post(
        "/auth/login",
        json={
            "email": built_in_iam_payload["admin_email"],
            "password": "Recoveredpass456",
        },
    )
    assert new_login.status_code == 200
