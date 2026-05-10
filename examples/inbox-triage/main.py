"""Inbox triage.

Reads the user's connected mailbox, asks the LLM to classify each
message, and returns a triage report. Each message is classified into
one of: urgent, response_needed, fyi, junk.
"""
from platform_sdk import ctx, tools

CATEGORIES = ("urgent", "response_needed", "fyi", "junk")


def run() -> dict:
    emails = tools.inbox.list_emails()
    ctx.log(f"fetched {len(emails)} emails")

    triaged: list[dict] = []
    counts = {c: 0 for c in CATEGORIES}

    for email in emails:
        prompt = (
            "Classify this email into exactly one category from "
            f"{list(CATEGORIES)}. Reply with only the category name.\n\n"
            f"From: {email['from']}\n"
            f"Subject: {email['subject']}\n"
            f"Body: {email['body']}"
        )
        result = tools.llm.complete(model="gpt-4o-mini", prompt=prompt, max_tokens=10)
        category = _normalize(result.text)
        counts[category] += 1
        triaged.append(
            {
                "from": email["from"],
                "subject": email["subject"],
                "category": category,
            }
        )

    return {
        "total": len(emails),
        "counts": counts,
        "triaged": triaged,
    }


def _normalize(text: str) -> str:
    cleaned = text.strip().lower().split()[0] if text.strip() else "junk"
    cleaned = cleaned.strip(".,!:;\"'")
    return cleaned if cleaned in CATEGORIES else "fyi"
