"""Pytest fixtures for the integration suite.

The suite assumes the compose stack is already up locally on the
default ports. Run with:

    pytest tests/integration -q

Set INTEGRATION_API_URL / INTEGRATION_MAILHOG_URL to point at a
different host if you're not on localhost.
"""
from __future__ import annotations

import os
import time

import httpx
import pytest


API_URL = os.environ.get("INTEGRATION_API_URL", "http://localhost:8000").rstrip("/")
MAILHOG_URL = os.environ.get("INTEGRATION_MAILHOG_URL", "http://localhost:8025").rstrip("/")


def _login(email: str, password: str) -> str:
    resp = httpx.post(
        f"{API_URL}/auth/login",
        json={"email": email, "password": password},
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _wait_for_health(url: str, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    last: Exception | None = None
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code == 200:
                return
        except httpx.HTTPError as e:
            last = e
        time.sleep(1)
    raise RuntimeError(f"{url} never became healthy: {last}")


@pytest.fixture(scope="session", autouse=True)
def _stack_up() -> None:
    _wait_for_health(f"{API_URL}/health")


@pytest.fixture(scope="session")
def admin_token() -> str:
    return _login("admin@demo.local", "demo-admin")


@pytest.fixture(scope="session")
def user_token() -> str:
    return _login("user@demo.local", "demo-user")


@pytest.fixture(scope="session")
def dev_token() -> str:
    return _login("dev@demo.local", "demo-dev")
