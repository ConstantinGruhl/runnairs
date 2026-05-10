from __future__ import annotations

import logging

from fastapi import FastAPI

from app import approvals
from app.tools import email, http, inbox, llm, postgres

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")

app = FastAPI(title="Agent Platform Tool Gateway")
app.include_router(llm.router)
app.include_router(email.router)
app.include_router(postgres.router)
app.include_router(http.router)
app.include_router(inbox.router)
app.include_router(approvals.router)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "tool-gateway"}
