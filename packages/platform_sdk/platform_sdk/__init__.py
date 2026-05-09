"""Agent SDK for the Enterprise AI Agent Platform.

Agents import this package and call platform-managed tools through it.
Every method is a thin HTTP call to the tool gateway, authenticated with
a short-lived run token. Agents never receive raw secrets, never make
external HTTP calls directly, and never bypass policy.

Currently exposed:
    tools.llm.complete(...)

Other surfaces (tools.email, tools.postgres, tools.http, secrets.get,
ctx.request_approval) land in later phases.
"""
from __future__ import annotations

from platform_sdk import tools  # noqa: F401
from platform_sdk.context import ctx  # noqa: F401

__all__ = ["tools", "ctx"]
__version__ = "0.1.0"
