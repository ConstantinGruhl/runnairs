from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin,
    approvals,
    auth,
    catalog,
    connections,
    dev,
    feedback,
    installations,
    me,
    runs,
    schedules,
    secrets,
)

app = FastAPI(title="Agent Platform Control Plane")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
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
