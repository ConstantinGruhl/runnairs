"""Customer briefing.

Combines internal pipeline data (Postgres) with the CRM record (HTTP)
into a one-page LLM-generated briefing for an account exec.
"""
from platform_sdk import ctx, tools

CRM_BASE = "http://mock-crm:8080"


def run() -> dict:
    customer_id = ctx.inputs["customer_id"]
    ctx.log(f"building briefing for customer={customer_id!r}")

    pipeline = tools.postgres.query(
        """
        SELECT name, stage, amount_usd, region, closes_on
        FROM opportunities
        WHERE customer_id = :customer
        ORDER BY closes_on
        """,
        {"customer": customer_id},
    )

    crm_resp = tools.http.get(f"{CRM_BASE}/customers/{customer_id}")
    if crm_resp.status_code == 404:
        return {
            "customer_id": customer_id,
            "error": "customer not found in CRM",
            "pipeline_count": len(pipeline),
        }
    if crm_resp.status_code >= 400:
        return {
            "customer_id": customer_id,
            "error": f"CRM returned {crm_resp.status_code}",
            "pipeline_count": len(pipeline),
        }

    crm = crm_resp.json()

    pipeline_lines = (
        "\n".join(
            f"- {p['name']} ({p['stage']}, ${p['amount_usd']:,.0f}, {p['region']}, "
            f"closes {p['closes_on']})"
            for p in pipeline
        )
        or "(no opportunities on file)"
    )
    briefing = tools.llm.complete(
        model="gpt-4o-mini",
        prompt=(
            "Write a brief 4-bullet customer briefing for an account exec, "
            "covering account profile, open pipeline, risks, and a recommended "
            "next step.\n\n"
            f"Account: {crm.get('name')} ({crm.get('tier')})\n"
            f"Owner: {crm.get('owner')}\n"
            f"Open opportunities (CRM): {crm.get('open_opportunities')}\n"
            f"Last contacted: {crm.get('last_contacted')}\n\n"
            f"Pipeline rows from internal DB:\n{pipeline_lines}"
        ),
    )

    return {
        "customer_id": customer_id,
        "customer_name": crm.get("name"),
        "tier": crm.get("tier"),
        "owner": crm.get("owner"),
        "pipeline_count": len(pipeline),
        "briefing": briefing.text,
        "tokens": briefing.tokens_used,
        "backend": briefing.backend,
    }
