"""LLM tool surface.

    >>> from platform_sdk import tools
    >>> tools.llm.complete(model="gpt-4o-mini", prompt="Hello")
    LlmCompletion(text=..., model=..., tokens_used=..., cost_usd=...)
"""
from __future__ import annotations

from dataclasses import dataclass

from platform_sdk import _client


@dataclass(frozen=True)
class LlmCompletion:
    text: str
    model: str
    tokens_used: int
    cost_usd: float
    backend: str  # "openai" | "stub"

    def __str__(self) -> str:
        return self.text


def complete(
    *,
    model: str,
    prompt: str,
    temperature: float | None = None,
    max_tokens: int | None = None,
    system: str | None = None,
) -> LlmCompletion:
    """Single-turn completion.

    Resolves the workspace's LLM API key on the gateway side; the agent
    never sees it. Returns the completion text plus usage metadata.
    """
    payload: dict[str, object] = {"model": model, "prompt": prompt}
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if system is not None:
        payload["system"] = system

    body = _client.post("/tools/llm/complete", payload)
    return LlmCompletion(
        text=body["text"],
        model=body["model"],
        tokens_used=int(body.get("tokens_used", 0)),
        cost_usd=float(body.get("cost_usd", 0.0)),
        backend=body.get("backend", "unknown"),
    )
