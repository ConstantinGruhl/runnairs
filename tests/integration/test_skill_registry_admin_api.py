from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.services import agent_deploy_service

from tests.integration.test_auth_sessions import (
    _complete_bootstrap,
    built_in_iam_client,
    built_in_iam_payload,
)


@pytest.fixture
def stub_skill_deploy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent_deploy_service, "_build_image", lambda context, tag: None)
    monkeypatch.setattr(
        agent_deploy_service,
        "inspect_image_package",
        lambda *, image_tag, entrypoint: {
            "modules": ["default"],
            "runtime_api": "v2",
        },
    )


@pytest.fixture(scope="session", autouse=True)
def _stack_up() -> None:
    return None


def test_admin_can_register_fetch_and_refresh_skill_source(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stub_skill_deploy: None,
) -> None:
    _complete_bootstrap(built_in_iam_client, built_in_iam_payload)
    monkeypatch.setattr(settings, "skill_registry_root", tmp_path / "registry")

    repo_root = tmp_path / "demo-source"
    _init_repo(repo_root)
    _write_package(repo_root, instructions="# Initial instructions\n")
    _commit_all(repo_root, "initial")
    first_sha = _git(repo_root, "rev-parse", "HEAD").strip()

    create_response = built_in_iam_client.put(
        "/admin/skill-sources/demo-skill",
        json={"repo_url": str(repo_root), "git_ref": "HEAD"},
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["slug"] == "demo-skill"
    assert created["resolved_commit_sha"] == first_sha
    assert created["status"] == "ready"
    assert created["instructions_markdown"] == "# Initial instructions\n"
    assert any(entry["path"] == "automation.yaml" for entry in created["tree"])

    list_response = built_in_iam_client.get("/admin/skill-sources")
    assert list_response.status_code == 200
    assert list_response.json()[0]["slug"] == "demo-skill"

    detail_response = built_in_iam_client.get("/admin/skill-sources/demo-skill")
    assert detail_response.status_code == 200
    assert detail_response.json()["manifest"]["name"] == "demo-skill"
    assert detail_response.json()["status"] == "ready"

    pending_agents = built_in_iam_client.get("/admin/agents/pending")
    assert pending_agents.status_code == 200
    first_agent = next(agent for agent in pending_agents.json()["agents"] if agent["slug"] == "demo-skill")
    assert first_agent["latest_version"] == "v1"

    _write_package(repo_root, instructions="# Refreshed instructions\n")
    _commit_all(repo_root, "refresh")
    second_sha = _git(repo_root, "rev-parse", "HEAD").strip()

    refresh_response = built_in_iam_client.post("/admin/skill-sources/demo-skill/refresh")
    assert refresh_response.status_code == 200
    refreshed = refresh_response.json()
    assert refreshed["resolved_commit_sha"] == second_sha
    assert refreshed["instructions_markdown"] == "# Refreshed instructions\n"

    pending_agents_after_refresh = built_in_iam_client.get("/admin/agents/pending")
    assert pending_agents_after_refresh.status_code == 200
    refreshed_agent = next(
        agent for agent in pending_agents_after_refresh.json()["agents"] if agent["slug"] == "demo-skill"
    )
    assert refreshed_agent["latest_version"] == "v2"


def test_non_admin_cannot_manage_skill_sources(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stub_skill_deploy: None,
) -> None:
    _complete_bootstrap(built_in_iam_client, built_in_iam_payload)
    monkeypatch.setattr(settings, "skill_registry_root", tmp_path / "registry")
    repo_root = tmp_path / "demo-source"
    _init_repo(repo_root)
    _write_package(repo_root)
    _commit_all(repo_root, "initial")

    create_user = built_in_iam_client.post(
        "/admin/users",
        json={"email": "dev@example.com", "password": "Developerpass123", "role": "developer"},
    )
    assert create_user.status_code == 201

    built_in_iam_client.post("/auth/logout")
    login = built_in_iam_client.post(
        "/auth/login",
        json={"email": "dev@example.com", "password": "Developerpass123"},
    )
    assert login.status_code == 200

    response = built_in_iam_client.put(
        "/admin/skill-sources/demo-skill",
        json={"repo_url": str(repo_root), "git_ref": "HEAD"},
    )
    assert response.status_code == 403


def test_rejects_slug_mismatch(
    built_in_iam_client: TestClient,
    built_in_iam_payload: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    stub_skill_deploy: None,
) -> None:
    _complete_bootstrap(built_in_iam_client, built_in_iam_payload)
    monkeypatch.setattr(settings, "skill_registry_root", tmp_path / "registry")

    repo_root = tmp_path / "demo-source"
    _init_repo(repo_root)
    _write_package(repo_root)
    _commit_all(repo_root, "initial")

    response = built_in_iam_client.put(
        "/admin/skill-sources/not-the-manifest-slug",
        json={"repo_url": str(repo_root), "git_ref": "HEAD"},
    )
    assert response.status_code == 422
    assert "manifest slug" in response.json()["detail"]


def _init_repo(repo_root: Path) -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "codex@example.com")
    _git(repo_root, "config", "user.name", "Codex")


def _write_package(repo_root: Path, *, instructions: str = "# Initial instructions\n") -> None:
    (repo_root / "automation.yaml").write_text(
        "\n".join(
            [
                "name: demo-skill",
                "display_name: Demo Skill",
                "description: Demo package",
                "entrypoint: main:run",
                "compatibility:",
                "  runtime_api: v2",
                "modules:",
                "  - id: default",
                "    title: Default",
                "    required: true",
                "    enabled_by_default: true",
                "tools: []",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "main.py").write_text("def run():\n    return {'ok': True}\n", encoding="utf-8")
    (repo_root / "AI_INSTRUCTIONS.md").write_text(instructions, encoding="utf-8")


def _commit_all(repo_root: Path, message: str) -> None:
    _git(repo_root, "add", ".")
    _git(repo_root, "commit", "-m", message)


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout
