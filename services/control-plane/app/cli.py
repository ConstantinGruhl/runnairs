"""Control-plane CLI.

Run inside the container:

    docker compose exec control-plane python -m app.cli ...

Subcommands grow as we go through the phases.
"""
from __future__ import annotations

import json
import uuid

import typer
from sqlalchemy import select

from app import run_tokens
from app.core.db import SessionLocal
from app.models import Tenant, User

cli = typer.Typer(no_args_is_help=True)


@cli.command("version")
def version() -> None:
    """Print the control-plane CLI version."""
    typer.echo("control-plane cli 0.1.0")


@cli.command("mint-run-token")
def mint_run_token(
    tenant_email: str = typer.Option(
        ..., "--tenant-email",
        help="Email of any user in the target tenant; the tenant id is looked up.",
    ),
    triggering_user_email: str | None = typer.Option(
        None, "--user-email",
        help="Optional triggering user; defaults to none (system-triggered).",
    ),
    tools: list[str] = typer.Option(
        [], "--tool",
        help="Tool name allowed for this run. Repeat for each tool.",
    ),
    secrets: list[str] = typer.Option(
        [], "--secret",
        help="Secret grant in the form NAME:scope (workspace|user). Repeat to add more.",
    ),
    ttl_minutes: int = typer.Option(30, "--ttl-minutes"),
) -> None:
    """Mint a run token. Useful for testing the SDK against the gateway."""
    if not tools:
        raise typer.BadParameter("--tool must be passed at least once")

    grants: list[dict[str, str]] = []
    for raw in secrets:
        if ":" not in raw:
            raise typer.BadParameter(f"--secret expects NAME:scope, got {raw!r}")
        name, scope = raw.rsplit(":", 1)
        if scope not in ("workspace", "user"):
            raise typer.BadParameter(
                f"--secret scope must be 'workspace' or 'user', got {scope!r}"
            )
        grants.append({"name": name, "scope": scope})

    with SessionLocal() as db:
        tenant_user = db.execute(
            select(User).where(User.email == tenant_email)
        ).scalar_one_or_none()
        if tenant_user is None:
            raise typer.BadParameter(f"no user found for --tenant-email {tenant_email}")
        tenant_id = tenant_user.tenant_id

        triggering_user_id: uuid.UUID | None = None
        if triggering_user_email:
            tu = db.execute(
                select(User).where(
                    User.email == triggering_user_email,
                    User.tenant_id == tenant_id,
                )
            ).scalar_one_or_none()
            if tu is None:
                raise typer.BadParameter(
                    f"no user {triggering_user_email!r} in tenant {tenant_id}"
                )
            triggering_user_id = tu.id

    token = run_tokens.mint(
        run_id=uuid.uuid4(),
        tenant_id=tenant_id,
        agent_id=None,
        agent_version_id=None,
        triggering_user_id=triggering_user_id,
        allowed_tools=tools,
        secret_grants=grants,
        ttl_minutes=ttl_minutes,
    )

    typer.echo(json.dumps({"run_token": token, "tenant_id": str(tenant_id)}))


if __name__ == "__main__":
    cli()
