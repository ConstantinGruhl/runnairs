from __future__ import annotations

import logging

from fastapi import FastAPI

from app import approvals
from app.tools import email, llm

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")

app = FastAPI(title="Agent Platform Tool Gateway")
app.include_router(llm.router)
app.include_router(email.router)
app.include_router(approvals.router)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "tool-gateway"}
