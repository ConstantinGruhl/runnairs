from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SkillSource, SkillSourceStatus
from app.services import agent_deploy_service
from app.services.package_descriptor import PackageDescriptor, load_package_descriptor

DEFAULT_MAX_FILE_BYTES = 256 * 1024
DEFAULT_MAX_TOTAL_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_FILE_COUNT = 200
INSTRUCTION_FILENAMES = ("AI_INSTRUCTIONS.md", "SKILL.md", "README.md")
IGNORED_ROOT_NAMES = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".next"}


class SkillRegistryError(Exception):
    """Raised when a Git-backed skill source cannot be inspected safely."""


@dataclass(frozen=True)
class SkillTreeEntry:
    path: str
    kind: str
    size_bytes: int | None = None


@dataclass(frozen=True)
class SkillRegistryInspection:
    descriptor: PackageDescriptor
    instructions_markdown: str
    tree_entries: list[dict[str, object]]
    total_bytes: int
    file_count: int


def list_skill_sources(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    ready_only: bool = False,
) -> list[SkillSource]:
    stmt = select(SkillSource).where(SkillSource.tenant_id == tenant_id)
    if ready_only:
        stmt = stmt.where(SkillSource.status == SkillSourceStatus.ready)
    return db.execute(stmt.order_by(SkillSource.created_at.desc())).scalars().all()


def get_skill_source(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    slug: str,
    ready_only: bool = False,
) -> SkillSource | None:
    stmt = select(SkillSource).where(
        SkillSource.tenant_id == tenant_id,
        SkillSource.slug == slug,
    )
    if ready_only:
        stmt = stmt.where(SkillSource.status == SkillSourceStatus.ready)
    return db.execute(stmt).scalar_one_or_none()


def upsert_skill_source(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    slug: str,
    repo_url: str,
    git_ref: str,
    created_by: uuid.UUID,
    storage_root: Path,
) -> SkillSource:
    source = get_skill_source(db, tenant_id=tenant_id, slug=slug)
    if source is None:
        source = SkillSource(
            tenant_id=tenant_id,
            slug=slug,
            display_name=slug,
            repo_url=repo_url,
            git_ref=git_ref,
            created_by=created_by,
        )
        db.add(source)
        db.flush()

    source.repo_url = repo_url
    source.git_ref = git_ref
    return refresh_skill_source(db, source=source, storage_root=storage_root, expected_slug=slug)


def refresh_skill_source(
    db: Session,
    *,
    source: SkillSource,
    storage_root: Path,
    expected_slug: str | None = None,
) -> SkillSource:
    source.status = SkillSourceStatus.pending
    source.last_error = None
    db.flush()
    try:
        inspection, resolved_commit_sha, destination = stage_checkout(
            repo_url=source.repo_url,
            git_ref=source.git_ref,
            storage_root=storage_root,
            storage_key=_storage_key(source.tenant_id, source.slug),
        )
        manifest_slug = inspection.descriptor.data["name"]
        locked_slug = expected_slug or source.slug
        if locked_slug is not None and manifest_slug != locked_slug:
            raise SkillRegistryError(
                f"manifest slug {manifest_slug!r} does not match requested source slug {locked_slug!r}"
            )
        source.slug = manifest_slug
        source.display_name = inspection.descriptor.data.get("display_name") or manifest_slug
        source.resolved_commit_sha = resolved_commit_sha
        source.descriptor_format = inspection.descriptor.format
        source.manifest_json = inspection.descriptor.data
        source.tree_json = inspection.tree_entries
        source.instructions_markdown = inspection.instructions_markdown
        source.extracted_root = str(destination)
        deployed = agent_deploy_service.deploy_from_directory(
            db,
            tenant_id=source.tenant_id,
            created_by=source.created_by,
            source_root=destination,
            code_archive_url=f"{source.repo_url}@{resolved_commit_sha}",
            commit=False,
        )
        source.agent_id = deployed.agent_id
        source.status = SkillSourceStatus.ready
        source.last_synced_at = datetime.now(timezone.utc)
        source.last_error = None
        return source
    except (SkillRegistryError, agent_deploy_service.DeployError) as exc:
        source.status = SkillSourceStatus.error
        source.last_error = str(exc)
        source.last_synced_at = datetime.now(timezone.utc)
        raise SkillRegistryError(str(exc)) from exc


def serialize_skill_source_summary(source: SkillSource) -> dict[str, object]:
    return {
        "slug": source.slug,
        "display_name": source.display_name,
        "repo_url": source.repo_url,
        "git_ref": source.git_ref,
        "resolved_commit_sha": source.resolved_commit_sha,
        "status": source.status.value,
        "descriptor_format": source.descriptor_format,
        "last_synced_at": source.last_synced_at,
        "last_error": source.last_error,
    }


def serialize_skill_source_detail(source: SkillSource) -> dict[str, object]:
    return {
        **serialize_skill_source_summary(source),
        "instructions_markdown": source.instructions_markdown,
        "manifest": source.manifest_json or {},
        "tree": source.tree_json or [],
    }


def clone_repository(*, repo_url: str, git_ref: str, destination: Path) -> str:
    if destination.exists():
        raise SkillRegistryError(f"destination already exists: {destination}")

    try:
        _run_git(["clone", repo_url, str(destination)])
        _run_git(["-C", str(destination), "checkout", git_ref])
        return _run_git(["-C", str(destination), "rev-parse", "HEAD"]).strip()
    except FileNotFoundError as exc:
        raise SkillRegistryError("git is not installed or not available on PATH") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise SkillRegistryError(stderr or "git command failed") from exc


def inspect_checkout(
    root: Path,
    *,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_file_count: int = DEFAULT_MAX_FILE_COUNT,
) -> SkillRegistryInspection:
    try:
        descriptor = load_package_descriptor(root)
    except ValueError as exc:
        raise SkillRegistryError(str(exc)) from exc

    tree_entries, total_bytes, file_count = build_tree_snapshot(
        root,
        max_file_bytes=max_file_bytes,
        max_total_bytes=max_total_bytes,
        max_file_count=max_file_count,
    )
    return SkillRegistryInspection(
        descriptor=descriptor,
        instructions_markdown=resolve_instruction_markdown(root, descriptor),
        tree_entries=tree_entries,
        total_bytes=total_bytes,
        file_count=file_count,
    )


def stage_checkout(
    *,
    repo_url: str,
    git_ref: str,
    storage_root: Path,
    storage_key: str,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_file_count: int = DEFAULT_MAX_FILE_COUNT,
) -> tuple[SkillRegistryInspection, str, Path]:
    with tempfile.TemporaryDirectory(prefix="skill-source-") as tmpdir:
        checkout_root = Path(tmpdir) / "repo"
        resolved_commit_sha = clone_repository(
            repo_url=repo_url,
            git_ref=git_ref,
            destination=checkout_root,
        )
        inspection = inspect_checkout(
            checkout_root,
            max_file_bytes=max_file_bytes,
            max_total_bytes=max_total_bytes,
            max_file_count=max_file_count,
        )
        destination = storage_root / storage_key / resolved_commit_sha
        copy_checkout(checkout_root, destination)
        return inspection, resolved_commit_sha, destination


def build_tree_snapshot(
    root: Path,
    *,
    max_file_bytes: int,
    max_total_bytes: int,
    max_file_count: int,
) -> tuple[list[dict[str, object]], int, int]:
    entries: list[SkillTreeEntry] = []
    total_bytes = 0
    file_count = 0

    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if _is_ignored(relative):
            continue

        if path.is_dir():
            entries.append(SkillTreeEntry(path=relative.as_posix(), kind="directory"))
            continue

        if not path.is_file():
            raise SkillRegistryError(f"unsupported filesystem entry in checkout: {relative.as_posix()}")

        size_bytes = path.stat().st_size
        if size_bytes > max_file_bytes:
            raise SkillRegistryError(
                f"file exceeds {max_file_bytes} bytes: {relative.as_posix()}"
            )

        total_bytes += size_bytes
        file_count += 1

        if total_bytes > max_total_bytes:
            raise SkillRegistryError(
                f"checkout exceeds {max_total_bytes} bytes in total size"
            )
        if file_count > max_file_count:
            raise SkillRegistryError(
                f"checkout exceeds {max_file_count} tracked files"
            )

        entries.append(
            SkillTreeEntry(
                path=relative.as_posix(),
                kind="file",
                size_bytes=size_bytes,
            )
        )

    return [entry.__dict__ for entry in entries], total_bytes, file_count


def resolve_instruction_markdown(root: Path, descriptor: PackageDescriptor) -> str:
    for name in INSTRUCTION_FILENAMES:
        path = root / name
        if path.exists() and path.is_file():
            return path.read_text(encoding="utf-8")
    return descriptor_fallback_instructions(descriptor)


def descriptor_fallback_instructions(descriptor: PackageDescriptor) -> str:
    manifest = descriptor.data
    modules = [
        f"- `{module['id']}`"
        for module in manifest.get("modules", [])
        if isinstance(module, dict) and module.get("id")
    ]
    tools = [
        f"- `{tool}`"
        for tool in manifest.get("tools", [])
        if isinstance(tool, str)
    ]
    sections = [
        f"# {manifest.get('display_name') or manifest['name']}",
        "",
        manifest.get("description") or "Git-backed automation package.",
        "",
        "Use the checked-out files in this package as the source of truth.",
        f"Entrypoint: `{manifest['entrypoint']}`",
    ]
    if modules:
        sections.extend(["", "Modules:", *modules])
    if tools:
        sections.extend(["", "Declared tools:", *tools])
    return "\n".join(sections).strip() + "\n"


def copy_checkout(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".next"),
    )


def _run_git(args: list[str]) -> str:
    completed = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def _is_ignored(relative: Path) -> bool:
    return any(part in IGNORED_ROOT_NAMES for part in relative.parts)


def _storage_key(tenant_id: uuid.UUID, slug: str) -> str:
    return f"{tenant_id}/{slug}"
