"""Seed script: creates the demo tenant and the admin/dev/user accounts.

Idempotent — running it twice does not duplicate rows.
Invoke from inside the control-plane container:

    python -m app.seed
"""
from __future__ import annotations

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import Tenant, User, UserRole

DEMO_TENANT_NAME = "Demo Workspace"
DEMO_USERS: list[tuple[str, str, UserRole]] = [
    ("admin@demo.local", "demo-admin", UserRole.admin),
    ("dev@demo.local", "demo-dev", UserRole.developer),
    ("user@demo.local", "demo-user", UserRole.user),
]


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

        for email, password, role in DEMO_USERS:
            existing = db.execute(
                select(User).where(User.tenant_id == tenant.id, User.email == email)
            ).scalar_one_or_none()
            if existing is not None:
                print(f"[seed] user exists: {email}")
                continue
            user = User(
                tenant_id=tenant.id,
                email=email,
                password_hash=hash_password(password),
                role=role,
            )
            db.add(user)
            print(f"[seed] created user {email} ({role.value}) — password: {password}")

        db.commit()


if __name__ == "__main__":
    seed()
