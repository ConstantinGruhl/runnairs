from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    admin,
    approvals,
    auth,
    bootstrap,
    catalog,
    connections,
    dev,
    feedback,
    installations,
    me,
    oidc,
    runs,
    schedules,
    secrets,
    skill_registry,
)
from app.core.db import SessionLocal
from app.services import bootstrap_service

app = FastAPI(title="Agent Platform Control Plane")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_BOOTSTRAP_OPEN_PATHS = {"/auth/login", "/auth/me", "/docs", "/openapi.json", "/redoc", "/health"}


@app.middleware("http")
async def enforce_bootstrap_mode(request, call_next):
    path = request.url.path.rstrip("/") or "/"
    if request.method == "OPTIONS" or path in _BOOTSTRAP_OPEN_PATHS or path.startswith("/bootstrap"):
        return await call_next(request)

    with SessionLocal() as db:
        if bootstrap_service.bootstrap_required(db):
            return JSONResponse(
                status_code=423,
                content={
                    "detail": "instance bootstrap incomplete; complete setup before using the platform",
                    "bootstrap_required": True,
                },
            )

    return await call_next(request)

app.include_router(auth.router)
app.include_router(bootstrap.router)
app.include_router(admin.router)
app.include_router(oidc.router)
app.include_router(oidc.auth_router)
app.include_router(skill_registry.router)
app.include_router(skill_registry.app_router)
app.include_router(connections.router)
app.include_router(installations.router)
app.include_router(secrets.router)
app.include_router(dev.router)
app.include_router(catalog.router)
app.include_router(runs.router)
app.include_router(approvals.router)
app.include_router(me.router)
app.include_router(feedback.router)
app.include_router(schedules.router)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "control-plane"}
