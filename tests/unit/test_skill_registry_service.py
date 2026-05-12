from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.services.package_descriptor import load_package_descriptor
from app.services.skill_registry_service import (
    SkillRegistryError,
    build_tree_snapshot,
    clone_repository,
    descriptor_fallback_instructions,
    inspect_checkout,
    resolve_instruction_markdown,
)


def test_resolve_instruction_markdown_prefers_ai_instructions(tmp_path: Path) -> None:
    _write_minimal_package(tmp_path)
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")
    (tmp_path / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
    (tmp_path / "AI_INSTRUCTIONS.md").write_text("# AI\n", encoding="utf-8")

    descriptor = load_package_descriptor(tmp_path)

    assert resolve_instruction_markdown(tmp_path, descriptor) == "# AI\n"


def test_descriptor_fallback_instructions_include_modules_and_tools(tmp_path: Path) -> None:
    _write_minimal_package(tmp_path, tools=["openai.responses"])

    descriptor = load_package_descriptor(tmp_path)
    fallback = descriptor_fallback_instructions(descriptor)

    assert "# Demo Skill" in fallback
    assert "Entrypoint: `main:run`" in fallback
    assert "- `default`" in fallback
    assert "- `openai.responses`" in fallback


def test_build_tree_snapshot_excludes_git_directory(tmp_path: Path) -> None:
    _write_minimal_package(tmp_path)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "child.txt").write_text("ok", encoding="utf-8")

    entries, total_bytes, file_count = build_tree_snapshot(
        tmp_path,
        max_file_bytes=1024,
        max_total_bytes=4096,
        max_file_count=20,
    )

    paths = {entry["path"] for entry in entries}
    assert ".git/config" not in paths
    assert "nested/child.txt" in paths
    assert total_bytes > 0
    assert file_count >= 3


def test_build_tree_snapshot_rejects_oversized_file(tmp_path: Path) -> None:
    _write_minimal_package(tmp_path)
    (tmp_path / "big.bin").write_bytes(b"x" * 20)

    with pytest.raises(SkillRegistryError, match="file exceeds 10 bytes"):
        build_tree_snapshot(
            tmp_path,
            max_file_bytes=10,
            max_total_bytes=4096,
            max_file_count=20,
        )


def test_clone_repository_returns_resolved_commit_sha(tmp_path: Path) -> None:
    repo_root = tmp_path / "source"
    repo_root.mkdir()
    _write_minimal_package(repo_root)
    _git(repo_root, "init")
    _git(repo_root, "config", "user.email", "codex@example.com")
    _git(repo_root, "config", "user.name", "Codex")
    _git(repo_root, "add", ".")
    _git(repo_root, "commit", "-m", "initial")
    expected_sha = _git(repo_root, "rev-parse", "HEAD").strip()

    clone_root = tmp_path / "clone"
    actual_sha = clone_repository(
        repo_url=str(repo_root),
        git_ref="HEAD",
        destination=clone_root,
    )

    assert actual_sha == expected_sha
    assert (clone_root / "automation.yaml").exists()


def test_inspect_checkout_requires_descriptor(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Missing manifest\n", encoding="utf-8")

    with pytest.raises(SkillRegistryError, match="archive is missing automation.yaml or agent.yaml"):
        inspect_checkout(tmp_path)


def _write_minimal_package(root: Path, *, tools: list[str] | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "automation.yaml").write_text(
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
                f"tools: {tools or []}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "main.py").write_text("def run():\n    return {'ok': True}\n", encoding="utf-8")


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout
