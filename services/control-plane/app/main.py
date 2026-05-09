from __future__ import annotations

from fastapi import FastAPI

from app.api import admin, auth, catalog, dev

app = FastAPI(title="Agent Platform Control Plane")

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(dev.router)
app.include_router(catalog.router)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "control-plane"}
