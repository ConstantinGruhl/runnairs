"""postgres tool surface.

    >>> from platform_sdk import tools
    >>> rows = tools.postgres.query(
    ...     "SELECT name, region FROM opportunities WHERE region = :region",
    ...     {"region": "EMEA"},
    ... )
"""
from __future__ import annotations

from typing import Any

from platform_sdk._client import post


def query(sql: str, params: dict[str, Any] | list[Any] | None = None) -> list[dict[str, Any]]:
    res = post("/tools/postgres/query", {"query": sql, "params": params})
    return list(res.get("rows", []))
