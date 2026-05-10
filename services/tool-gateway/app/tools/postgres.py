"""tools.postgres.query — read-only access to the workspace's sample data DB.

For the prototype there's a single connection (SAMPLE_DB_URL). Real
deployments would expose multiple aliased connections, each gated by
its own secret grant.
"""
from __future__ import annotations

import logging
import time
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app import audit
from app.auth import RunClaims
from app.config import settings
from app.policy import ensure_tool_allowed

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tools/postgres", tags=["postgres"])

TOOL_NAME = "postgres.query"
_ROW_LIMIT = 1000
_FORBIDDEN_TOKENS = (
    "insert ", "update ", "delete ", "drop ", "truncate ", "alter ",
    "grant ", "revoke ", "create ",
)


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    params: list[Any] | dict[str, Any] | None = None


class QueryResponse(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int


_engine: Engine | None = None


def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        if not settings.sample_db_url:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "no sample DB configured (SAMPLE_DB_URL is empty)",
            )
        _engine = create_engine(settings.sample_db_url, pool_pre_ping=True, future=True)
    return _engine


@router.post("/query", response_model=QueryResponse)
def query(payload: QueryRequest, claims: RunClaims) -> QueryResponse:
    ensure_tool_allowed(claims, TOOL_NAME)

    lowered = payload.query.lower()
    if any(tok in lowered for tok in _FORBIDDEN_TOKENS):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "postgres.query is read-only; mutations are not permitted",
        )

    start = time.perf_counter()
    columns: list[str] = []
    rows: list[dict[str, Any]] = []
    error: Exception | None = None
    try:
        with _get_engine().connect() as conn:
            result = conn.execute(text(payload.query), payload.params or {})
            columns = list(result.keys())
            for i, row in enumerate(result.mappings()):
                if i >= _ROW_LIMIT:
                    break
                rows.append({k: _coerce(v) for k, v in row.items()})
    except Exception as e:  # noqa: BLE001
        error = e

    duration_ms = int((time.perf_counter() - start) * 1000)
    if error is not None:
        audit.write(
            claims=claims,
            tool_name=TOOL_NAME,
            args={"query_preview": payload.query[:200]},
            result_summary=f"error: {error}",
            status="error",
            duration_ms=duration_ms,
            cost_usd=Decimal("0"),
        )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"query failed: {error}")

    audit.write(
        claims=claims,
        tool_name=TOOL_NAME,
        args={"query_preview": payload.query[:200], "param_count": _param_count(payload.params)},
        result_summary=f"{len(rows)} rows × {len(columns)} cols",
        status="ok",
        duration_ms=duration_ms,
        cost_usd=Decimal("0"),
    )
    return QueryResponse(columns=columns, rows=rows, row_count=len(rows))


def _coerce(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    return v


def _param_count(params: list | dict | None) -> int:
    if params is None:
        return 0
    return len(params)
