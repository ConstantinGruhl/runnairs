"""Weekly sales summary (Phase 5 stub).

Phase 8 will add real Postgres + email + approval. For now this is the
canonical example used to test platform-cli deploy: it uses tools.llm
only and returns a stringly-typed summary.
"""
from platform_sdk import ctx, tools


def run() -> dict:
    region = ctx.inputs["region"]
    recipient = ctx.inputs.get("recipient_email")
    ctx.log(f"summarizing pipeline for region={region!r} recipient={recipient!r}")

    summary = tools.llm.complete(
        model="gpt-4o-mini",
        prompt=(
            f"You are a sales analyst. Write a 3-bullet summary of fictitious "
            f"pipeline activity for the {region} region. Each bullet 1 line."
        ),
    )

    return {
        "region": region,
        "recipient_email": recipient,
        "summary": summary.text,
        "tokens": summary.tokens_used,
        "backend": summary.backend,
    }
