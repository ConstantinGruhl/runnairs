from platform_sdk import ctx, tools


def run() -> dict:
    greeting = ctx.inputs.get("greeting", "Hello")
    ctx.log(f"received greeting: {greeting!r}")

    result = tools.llm.complete(
        model="gpt-4o-mini",
        prompt=f"{greeting}, agent platform! Reply in exactly five words.",
    )

    return {
        "text": result.text,
        "tokens": result.tokens_used,
        "backend": result.backend,
        "cost_usd": result.cost_usd,
    }
