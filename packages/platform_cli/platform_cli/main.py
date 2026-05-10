"""platform-cli - developer CLI for deploying automations to the platform."""
from __future__ import annotations

import getpass
import io
import json
import os
import zipfile
from pathlib import Path
from typing import Any

import typer
import yaml

from platform_cli import _api, _config

cli = typer.Typer(no_args_is_help=True, help=__doc__)


@cli.command("login")
def login(
    email: str = typer.Option(..., "--email"),
    api_url: str = typer.Option("http://localhost:8000", "--api-url"),
    password: str | None = typer.Option(
        None,
        "--password",
        help="If omitted, reads from stdin (or PLATFORM_CLI_PASSWORD env var).",
    ),
) -> None:
    """Authenticate against the control plane and persist the session."""
    if password is None:
        password = os.environ.get("PLATFORM_CLI_PASSWORD") or getpass.getpass("Password: ")

    try:
        body = _api.post_json(api_url, "/auth/login", body={"email": email, "password": password})
    except _api.ApiError as e:
        typer.secho(f"login failed: {e.detail}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    user = body["user"]
    cfg = _config.CliConfig(
        api_url=api_url.rstrip("/"),
        token=body["access_token"],
        email=user["email"],
        role=user["role"],
        tenant_id=user["tenant_id"],
    )
    cfg.save()
    typer.echo(f"signed in as {user['email']} ({user['role']}) - config saved")


@cli.command("logout")
def logout() -> None:
    """Forget the current CLI session."""
    _config.clear_config()
    typer.echo("signed out")


@cli.command("init")
def init(
    name: str = typer.Argument(..., help="Slug for the new automation (lowercase, hyphens)."),
    target: Path = typer.Option(Path.cwd(), "--target", help="Directory to create the automation in."),
) -> None:
    """Scaffold a new automation directory with automation.yaml + main.py."""
    if not name.replace("-", "").isalnum() or not name.islower():
        typer.secho("name must be lowercase alphanumeric with hyphens", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    out_dir = target / name
    if out_dir.exists():
        typer.secho(f"{out_dir} already exists", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    out_dir.mkdir(parents=True)

    files = render_automation_template(
        slug=name,
        display_name=name.replace("-", " ").title(),
        modules=["default"],
    )
    for relative_path, content in files.items():
        destination = out_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")

    typer.echo(f"created {out_dir}")
    typer.echo(f"Edit automation.yaml and main.py, then run `platform-cli deploy ./{name}`")


@cli.command("deploy")
def deploy(
    path: Path = typer.Argument(Path.cwd(), help="Path to the automation directory."),
) -> None:
    """Zip the automation directory and deploy it to the control plane."""
    cfg = _try_load_config()
    if cfg.role not in ("developer", "admin"):
        typer.secho(
            f"role {cfg.role!r} cannot deploy automations (developer or admin required)",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(2)

    path = path.resolve()
    manifest_path = _find_manifest_path(path)
    if manifest_path is None:
        typer.secho(
            f"{path} is missing automation.yaml or agent.yaml",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(2)
    if not (path / "main.py").exists():
        typer.secho(f"{path}/main.py not found", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        typer.secho(f"{manifest_path.name} parse error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    if not isinstance(manifest, dict):
        typer.secho(
            f"{manifest_path.name} must be a mapping at the top level",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(2)
    for required in ("name", "entrypoint"):
        if not manifest.get(required):
            typer.secho(
                f"{manifest_path.name} missing required field: {required}",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(2)

    typer.echo(f"deploying {manifest['name']} from {path}")
    zip_bytes = _zip_directory(path)
    typer.echo(f"uploading {len(zip_bytes)} bytes")

    try:
        body = _api.post_multipart(
            cfg.api_url,
            "/dev/agents/deploy",
            files={"archive": ("agent.zip", zip_bytes, "application/zip")},
            token=cfg.token,
            timeout=300.0,
        )
    except _api.ApiError as e:
        typer.secho(f"deploy failed: {e.detail}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    typer.echo(
        f"deployed {body['slug']} {body['version']} "
        f"(agent_id={body['agent_id']}, image_tag={body['image_tag']})"
    )
    if body.get("status") == "draft":
        typer.echo("note: automation is draft; an admin must approve it before end users can run it")


@cli.command("runs")
def runs(
    run_id: str = typer.Argument(...),
) -> None:
    """Print the JSON of a run by id."""
    cfg = _try_load_config()
    body = _api.get_json(cfg.api_url, f"/runs/{run_id}", token=cfg.token)
    typer.echo(json.dumps(body, indent=2, default=str))


def _try_load_config() -> _config.CliConfig:
    try:
        return _config.CliConfig.load()
    except RuntimeError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(2)


def _zip_directory(path: Path) -> bytes:
    buf = io.BytesIO()
    skip_dirs = {".venv", "__pycache__", ".git", "node_modules", ".mypy_cache", ".pytest_cache"}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for entry in sorted(path.rglob("*")):
            if entry.is_dir():
                continue
            if any(part in skip_dirs or part.startswith(".") for part in entry.relative_to(path).parts[:-1]):
                continue
            arc = entry.relative_to(path).as_posix()
            zf.write(entry, arcname=arc)
    return buf.getvalue()


def _find_manifest_path(path: Path) -> Path | None:
    for name in ("automation.yaml", "agent.yaml"):
        manifest_path = path / name
        if manifest_path.exists():
            return manifest_path
    return None


def render_automation_template(*, slug: str, display_name: str, modules: list[str]) -> dict[str, str]:
    return {
        "automation.yaml": render_automation_yaml(
            slug=slug,
            display_name=display_name,
            modules=modules,
        ),
        "main.py": render_automation_main(modules=modules),
        "README.md": _README_TEMPLATE.format(display_name=display_name),
        "AI_INSTRUCTIONS.md": _AI_INSTRUCTIONS_TEMPLATE,
        "tests/test_agent.py": _TEST_TEMPLATE,
    }


def render_automation_yaml(*, slug: str, display_name: str, modules: list[str]) -> str:
    return yaml.safe_dump(
        {
            "name": slug,
            "display_name": display_name,
            "description": f"TODO - describe what {display_name} does.",
            "runtime": "python3.12",
            "entrypoint": "main:run",
            "compatibility": {"runtime_api": "v2"},
            "inputs": {},
            "modules": [
                {
                    "id": module_id,
                    "title": module_id.replace("_", " ").title(),
                    "required": index == 0,
                    "enabled_by_default": True,
                }
                for index, module_id in enumerate(modules)
            ],
            "tools": [],
            "limits": {
                "timeout_seconds": 60,
                "memory_mb": 256,
                "max_tokens": 5000,
                "max_cost_usd": 0.50,
            },
        },
        sort_keys=False,
    )


def render_automation_main(*, modules: list[str]) -> str:
    meta: dict[str, Any] = {
        "runtime_api": "v2",
        "modules": [{"id": module_id} for module_id in modules],
        "triggers": ["manual"],
    }
    return (
        "AUTOMATION_META = " + json.dumps(meta, indent=2) + "\n\n"
        + "def run() -> dict:\n"
        + '    return {"ok": True}\n'
    )


_README_TEMPLATE = """# {display_name}

Native automation package scaffolded by `platform-cli init`.
"""

_AI_INSTRUCTIONS_TEMPLATE = """Build inside the declared module boundaries.
Prefer updating `automation.yaml` over adding sidecar config files when metadata changes.
"""

_TEST_TEMPLATE = """from main import run


def test_run_returns_ok() -> None:
    assert run()["ok"] is True
"""


if __name__ == "__main__":
    cli()
