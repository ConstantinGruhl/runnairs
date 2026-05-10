"""Weekly sales summary.

Asks an LLM for a 3-bullet summary, pauses for human approval, and
emails the result if approved. Phase 8 will swap the LLM-fabricated
pipeline for a real Postgres query.
"""
from platform_sdk import ctx, tools


def run() -> dict:
    region = ctx.inputs["region"]
    recipient = ctx.inputs["recipient_email"]
    ctx.log(f"summarizing pipeline for region={region!r} → {recipient!r}")

    summary = tools.llm.complete(
        model="gpt-4o-mini",
        prompt=(
            f"You are a sales analyst. Write a 3-bullet summary of fictitious "
            f"pipeline activity for the {region} region. Each bullet on its own "
            f"line, prefixed with '- '."
        ),
    )

    approval = ctx.request_approval(
        action="email.send",
        title=f"Email weekly summary to {recipient}?",
        body=summary.text,
        payload={"region": region, "recipient": recipient},
    )

    if not approval.approved:
        ctx.log(f"approval not granted (status={approval.status}); skipping email", level="warn")
        return {
            "region": region,
            "recipient_email": recipient,
            "summary": summary.text,
            "tokens": summary.tokens_used,
            "backend": summary.backend,
            "email_sent": False,
            "approval_status": approval.status,
        }

    tools.email.send(
        to=recipient,
        subject=f"Weekly Sales Summary — {region}",
        body=summary.text,
    )
    ctx.log(f"email delivered to {recipient}")

    return {
        "region": region,
        "recipient_email": recipient,
        "summary": summary.text,
        "tokens": summary.tokens_used,
        "backend": summary.backend,
        "email_sent": True,
        "approval_status": approval.status,
    }
