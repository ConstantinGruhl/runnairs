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


def test_ready_skill_sources_are_visible_from_app_routes(
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

    create_response = built_in_iam_client.put(
        "/admin/skill-sources/demo-skill",
        json={"repo_url": str(repo_root), "git_ref": "HEAD"},
    )
    assert create_response.status_code == 200

    list_response = built_in_iam_client.get("/app/skills")
    assert list_response.status_code == 200
    assert list_response.json()[0]["slug"] == "demo-skill"

    detail_response = built_in_iam_client.get("/app/skills/demo-skill")
    assert detail_response.status_code == 200
    body = detail_response.json()
    assert body["instructions_markdown"] == "# Initial instructions\n"
    assert any(entry["path"] == "automation.yaml" for entry in body["tree"])


def _init_repo(repo_root: Path) -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "codex@example.com")
    _git(repo_root, "config", "user.name", "Codex")


def _write_package(repo_root: Path) -> None:
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
    (repo_root / "AI_INSTRUCTIONS.md").write_text("# Initial instructions\n", encoding="utf-8")


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
