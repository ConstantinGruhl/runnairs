"""HTTP surface for tools.llm.complete."""
from __future__ import annotations

import logging
import time
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app import audit, secrets
from app.auth import RunClaims
from app.policy import ensure_tool_allowed
from app.tools import llm_openai

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tools/llm", tags=["llm"])

TOOL_NAME = "llm.complete"


class CompleteRequest(BaseModel):
    model: str
    prompt: str = Field(min_length=1)
    system: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None


class CompleteResponse(BaseModel):
    text: str
    model: str
    tokens_used: int
    cost_usd: float
    backend: str


@router.post("/complete", response_model=CompleteResponse)
def complete(payload: CompleteRequest, claims: RunClaims) -> CompleteResponse:
    ensure_tool_allowed(claims, TOOL_NAME)

    start = time.perf_counter()
    api_key: str | None = None
    used_secret_value: str | None = None
    try:
        used_secret_value = secrets.resolve(claims, "OPENAI_API_KEY")
        api_key = used_secret_value
    except secrets.SecretResolutionError:
        logger.warning(
            "no OPENAI_API_KEY available for tenant=%s; using stub backend",
            claims.tenant_id,
        )
        api_key = None

    error: Exception | None = None
    result: llm_openai.CompletionResult | None = None
    try:
        if api_key:
            result = llm_openai.real_complete(
                api_key=api_key,
                model=payload.model,
                prompt=payload.prompt,
                system=payload.system,
                temperature=payload.temperature,
                max_tokens=payload.max_tokens,
            )
        else:
            result = llm_openai.stub_complete(
                model=payload.model,
                prompt=payload.prompt,
                system=payload.system,
                max_tokens=payload.max_tokens,
            )
    except Exception as e:  # noqa: BLE001 — gateway should not crash the request loop
        error = e

    duration_ms = int((time.perf_counter() - start) * 1000)
    secret_values_to_redact = [used_secret_value] if used_secret_value else []

    if error is not None:
        audit.write(
            claims=claims,
            tool_name=TOOL_NAME,
            args=payload.model_dump(exclude={"prompt", "system"}) | {
                "prompt_preview": payload.prompt[:120],
            },
            result_summary=None,
            status="error",
            duration_ms=duration_ms,
            cost_usd=Decimal("0"),
            secret_values=secret_values_to_redact,
        )
        logger.exception("llm.complete failed", exc_info=error)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"upstream LLM call failed: {error}",
        )

    assert result is not None
    audit.write(
        claims=claims,
        tool_name=TOOL_NAME,
        args=payload.model_dump(exclude={"prompt", "system"}) | {
            "prompt_preview": payload.prompt[:120],
            "system_present": payload.system is not None,
            "backend": result.backend,
        },
        result_summary=f"{result.input_tokens + result.output_tokens} tokens, "
                       f"backend={result.backend}",
        status="ok",
        duration_ms=duration_ms,
        cost_usd=result.cost_usd,
        secret_values=secret_values_to_redact,
    )

    return CompleteResponse(
        text=result.text,
        model=result.model,
        tokens_used=result.input_tokens + result.output_tokens,
        cost_usd=float(result.cost_usd),
        backend=result.backend,
    )
