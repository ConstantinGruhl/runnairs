"""Weekly sales summary.

Pulls real opportunity rows from the workspace's Postgres, has the LLM
write a 3-bullet summary, then asks a human to approve before emailing
it out.
"""
from platform_sdk import ctx, tools


def run() -> dict:
    region = ctx.inputs["region"]
    recipient = ctx.inputs["recipient_email"]
    ctx.log(f"summarizing pipeline for region={region!r} → {recipient!r}")

    rows = tools.postgres.query(
        """
        SELECT name, stage, amount_usd, closes_on
        FROM opportunities
        WHERE region = :region
        ORDER BY amount_usd DESC
        """,
        {"region": region},
    )
    if not rows:
        return {
            "region": region,
            "recipient_email": recipient,
            "summary": f"No opportunities found for region {region}.",
            "tokens": 0,
            "backend": "n/a",
            "email_sent": False,
            "approval_status": "skipped",
            "row_count": 0,
        }

    formatted = "\n".join(
        f"- {r['name']} ({r['stage']}, ${r['amount_usd']:,.0f}, closes {r['closes_on']})"
        for r in rows
    )
    summary = tools.llm.complete(
        model="gpt-4o-mini",
        prompt=(
            f"You are a sales analyst. Summarize the {region} pipeline for "
            f"leadership in 3 bullets, calling out the largest deal, the "
            f"riskiest stage, and the soonest close. Keep each bullet to one "
            f"line. Source rows:\n\n{formatted}"
        ),
    )

    approval = ctx.request_approval(
        action="email.send",
        title=f"Email weekly summary to {recipient}?",
        body=summary.text,
        payload={"region": region, "recipient": recipient, "row_count": len(rows)},
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
            "row_count": len(rows),
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
        "row_count": len(rows),
    }
