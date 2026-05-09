"""OpenAI integration + deterministic stub fallback."""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from decimal import Decimal

logger = logging.getLogger(__name__)

# USD per 1K tokens, approximate. Used for cost reporting and budget
# enforcement. Fine to be wrong at the second-decimal level — the
# control plane does the actual enforcement against a budget cap.
_PRICES = {
    "gpt-4o": (Decimal("0.005"), Decimal("0.015")),
    "gpt-4o-mini": (Decimal("0.00015"), Decimal("0.0006")),
    "gpt-4-turbo": (Decimal("0.01"), Decimal("0.03")),
    "gpt-3.5-turbo": (Decimal("0.0005"), Decimal("0.0015")),
}


@dataclass(frozen=True)
class CompletionResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    backend: str  # "openai" | "stub"


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    prices = _PRICES.get(model)
    if prices is None:
        return Decimal("0")
    in_price, out_price = prices
    return (Decimal(input_tokens) / 1000 * in_price) + (
        Decimal(output_tokens) / 1000 * out_price
    )


def stub_complete(
    *,
    model: str,
    prompt: str,
    system: str | None,
    max_tokens: int | None,
) -> CompletionResult:
    """Deterministic completion used when no OPENAI_API_KEY is configured.

    Returns a short echo so demos and tests run without spending tokens
    or requiring network access. The hash makes it deterministic per
    prompt for snapshot tests.
    """
    digest = hashlib.sha256(((system or "") + "\n" + prompt).encode()).hexdigest()[:8]
    text = f"[stub:{model}:{digest}] " + prompt[:200].strip()
    if max_tokens:
        text = text[: max_tokens * 4]
    input_tokens = max(1, (len(prompt) + len(system or "")) // 4)
    output_tokens = max(1, len(text) // 4)
    return CompletionResult(
        text=text,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=Decimal("0"),
        backend="stub",
    )


def real_complete(
    *,
    api_key: str,
    model: str,
    prompt: str,
    system: str | None,
    temperature: float | None,
    max_tokens: int | None,
) -> CompletionResult:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    kwargs: dict[str, object] = {"model": model, "messages": messages}
    if temperature is not None:
        kwargs["temperature"] = temperature
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

    response = client.chat.completions.create(**kwargs)
    choice = response.choices[0]
    text = choice.message.content or ""
    usage = response.usage
    input_tokens = usage.prompt_tokens if usage else 0
    output_tokens = usage.completion_tokens if usage else 0
    return CompletionResult(
        text=text,
        model=response.model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=estimate_cost(model, input_tokens, output_tokens),
        backend="openai",
    )
