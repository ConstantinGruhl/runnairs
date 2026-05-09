"""Seed script: demo tenant, admin/dev/user accounts, hello-world agent.

Idempotent — running it twice does not duplicate rows.
Invoke from inside the control-plane container:

    python -m app.seed
"""
from __future__ import annotations

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import Agent, AgentStatus, AgentVersion, Tenant, User, UserRole

DEMO_TENANT_NAME = "Demo Workspace"
DEMO_USERS: list[tuple[str, str, UserRole]] = [
    ("admin@demo.local", "demo-admin", UserRole.admin),
    ("dev@demo.local", "demo-dev", UserRole.developer),
    ("user@demo.local", "demo-user", UserRole.user),
]

HELLO_WORLD_MANIFEST: dict = {
    "name": "hello-world",
    "display_name": "Hello World",
    "description": "Smallest possible agent — calls llm.complete and returns the result.",
    "runtime": "python3.12",
    "entrypoint": "main:run",
    "inputs": {"greeting": {"type": "string", "required": False}},
    "permissions": {
        "tools": ["llm.complete"],
        "secrets": [{"name": "OPENAI_API_KEY", "scope": "workspace"}],
    },
    "limits": {
        "timeout_seconds": 30,
        "memory_mb": 256,
        "max_tokens": 1000,
        "max_cost_usd": 0.10,
    },
}
HELLO_WORLD_IMAGE_TAG = "platform/hello-world:v1"
HELLO_WORLD_VERSION = "v1"


def seed() -> None:
    with SessionLocal() as db:
        tenant = db.execute(
            select(Tenant).where(Tenant.name == DEMO_TENANT_NAME)
        ).scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(name=DEMO_TENANT_NAME)
            db.add(tenant)
            db.flush()
            print(f"[seed] created tenant {tenant.name} ({tenant.id})")
        else:
            print(f"[seed] tenant exists: {tenant.name} ({tenant.id})")

        users_by_email: dict[str, User] = {}
        for email, password, role in DEMO_USERS:
            existing = db.execute(
                select(User).where(User.tenant_id == tenant.id, User.email == email)
            ).scalar_one_or_none()
            if existing is not None:
                users_by_email[email] = existing
                print(f"[seed] user exists: {email}")
                continue
            user = User(
                tenant_id=tenant.id,
                email=email,
                password_hash=hash_password(password),
                role=role,
            )
            db.add(user)
            db.flush()
            users_by_email[email] = user
            print(f"[seed] created user {email} ({role.value}) — password: {password}")

        dev_user = users_by_email["dev@demo.local"]
        admin_user = users_by_email["admin@demo.local"]

        agent = db.execute(
            select(Agent).where(Agent.tenant_id == tenant.id, Agent.slug == "hello-world")
        ).scalar_one_or_none()
        if agent is None:
            agent = Agent(
                tenant_id=tenant.id,
                slug="hello-world",
                name=HELLO_WORLD_MANIFEST["display_name"],
                description=HELLO_WORLD_MANIFEST["description"],
                created_by=dev_user.id,
                status=AgentStatus.draft,
            )
            db.add(agent)
            db.flush()
            print(f"[seed] created agent hello-world ({agent.id})")
        else:
            print(f"[seed] agent exists: hello-world ({agent.id})")

        version = db.execute(
            select(AgentVersion).where(
                AgentVersion.agent_id == agent.id,
                AgentVersion.version == HELLO_WORLD_VERSION,
            )
        ).scalar_one_or_none()
        if version is None:
            from datetime import datetime, timezone
            version = AgentVersion(
                agent_id=agent.id,
                version=HELLO_WORLD_VERSION,
                manifest_json=HELLO_WORLD_MANIFEST,
                image_tag=HELLO_WORLD_IMAGE_TAG,
                created_by=dev_user.id,
                approved_by=admin_user.id,
                approved_at=datetime.now(timezone.utc),
            )
            db.add(version)
            db.flush()
            agent.current_version_id = version.id
            agent.status = AgentStatus.approved
            print(f"[seed] created hello-world {HELLO_WORLD_VERSION} (image={HELLO_WORLD_IMAGE_TAG})")
        else:
            print(f"[seed] hello-world {HELLO_WORLD_VERSION} exists")

        db.commit()


if __name__ == "__main__":
    seed()
