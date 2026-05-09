"""platform-cli — developer CLI for deploying agents to the platform."""
from __future__ import annotations

import getpass
import io
import json
import os
import zipfile
from pathlib import Path

import typer
import yaml

from platform_cli import _api, _config

cli = typer.Typer(no_args_is_help=True, help=__doc__)


@cli.command("login")
def login(
    email: str = typer.Option(..., "--email"),
    api_url: str = typer.Option("http://localhost:8000", "--api-url"),
    password: str | None = typer.Option(
        None, "--password",
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
    typer.echo(f"signed in as {user['email']} ({user['role']}) — config saved")


@cli.command("logout")
def logout() -> None:
    """Forget the current CLI session."""
    _config.clear_config()
    typer.echo("signed out")


@cli.command("init")
def init(
    name: str = typer.Argument(..., help="Slug for the new agent (lowercase, hyphens)."),
    target: Path = typer.Option(Path.cwd(), "--target", help="Directory to create the agent in."),
) -> None:
    """Scaffold a new agent directory with agent.yaml + main.py."""
    if not name.replace("-", "").isalnum() or not name.islower():
        typer.secho("name must be lowercase alphanumeric with hyphens", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    out_dir = target / name
    if out_dir.exists():
        typer.secho(f"{out_dir} already exists", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    out_dir.mkdir(parents=True)

    (out_dir / "agent.yaml").write_text(_AGENT_YAML_TEMPLATE.format(name=name))
    (out_dir / "main.py").write_text(_MAIN_PY_TEMPLATE)
    (out_dir / "requirements.txt").write_text("# extra Python deps for this agent\n")

    typer.echo(f"created {out_dir}")
    typer.echo(f"Edit agent.yaml and main.py, then run `platform-cli deploy ./{name}`")


@cli.command("deploy")
def deploy(
    path: Path = typer.Argument(Path.cwd(), help="Path to the agent directory."),
) -> None:
    """Zip the agent directory and deploy it to the control plane."""
    cfg = _try_load_config()
    if cfg.role not in ("developer", "admin"):
        typer.secho(
            f"role {cfg.role!r} cannot deploy agents (developer or admin required)",
            fg=typer.colors.RED, err=True,
        )
        raise typer.Exit(2)

    path = path.resolve()
    if not (path / "agent.yaml").exists():
        typer.secho(f"{path}/agent.yaml not found", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    if not (path / "main.py").exists():
        typer.secho(f"{path}/main.py not found", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    # Sanity-validate manifest locally before uploading.
    try:
        manifest = yaml.safe_load((path / "agent.yaml").read_text()) or {}
    except yaml.YAMLError as e:
        typer.secho(f"agent.yaml parse error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    for required in ("name", "entrypoint"):
        if not manifest.get(required):
            typer.secho(f"agent.yaml missing required field: {required}", fg=typer.colors.RED, err=True)
            raise typer.Exit(2)

    typer.echo(f"deploying {manifest['name']} from {path}")
    zip_bytes = _zip_directory(path)
    typer.echo(f"uploading {len(zip_bytes)} bytes")

    try:
        body = _api.post_multipart(
            cfg.api_url, "/dev/agents/deploy",
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
        typer.echo("note: agent is draft; an admin must approve it before end users can run it")


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


_AGENT_YAML_TEMPLATE = """\
name: {name}
display_name: {name}
description: TODO — what does this agent do?
runtime: python3.12
entrypoint: main:run

inputs: {{}}

permissions:
  tools:
    - llm.complete
  secrets:
    - name: OPENAI_API_KEY
      scope: workspace

limits:
  timeout_seconds: 60
  memory_mb: 256
  max_tokens: 5000
  max_cost_usd: 0.50
"""

_MAIN_PY_TEMPLATE = '''from platform_sdk import ctx, tools


def run() -> dict:
    result = tools.llm.complete(
        model="gpt-4o-mini",
        prompt="Say hello in five words.",
    )
    return {"text": result.text, "tokens": result.tokens_used}
'''


if __name__ == "__main__":
    cli()
