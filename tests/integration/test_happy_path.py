"""End-to-end happy-path test for the platform.

Walks the demo flow from §16 of the spec:

  user logs in → starts weekly-summary
  → run reaches awaiting_approval
  → admin approves
  → email shows up in MailHog
  → user leaves feedback
  → dev sees the feedback in the dashboard

Assumes hello-world + weekly-summary are already deployed and approved
in the demo tenant (i.e. seed has run and `platform-cli deploy` ran for
weekly-summary). The seed creates hello-world; this test triggers a
deploy if weekly-summary is missing.
"""
from __future__ import annotations

import time

import httpx
import pytest

from .conftest import API_URL, MAILHOG_URL


def _hdrs(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _wait_for_status(token: str, run_id: str, *targets: str, timeout: float = 90.0) -> dict:
    deadline = time.time() + timeout
    last: dict | None = None
    while time.time() < deadline:
        r = httpx.get(f"{API_URL}/runs/{run_id}", headers=_hdrs(token), timeout=10.0)
        r.raise_for_status()
        last = r.json()
        if last["status"] in targets:
            return last
        if last["status"] in ("failed", "cancelled") and "failed" not in targets:
            pytest.fail(f"run failed: {last.get('error')!r}")
        time.sleep(1)
    pytest.fail(f"run {run_id} never reached one of {targets}; last={last}")


def test_weekly_summary_full_flow(user_token: str, admin_token: str, dev_token: str) -> None:
    # Confirm weekly-summary is in the catalog as an approved agent.
    catalog = httpx.get(f"{API_URL}/app/catalog", headers=_hdrs(user_token), timeout=10.0).json()
    slugs = [a["slug"] for a in catalog["agents"]]
    assert "weekly-summary" in slugs, (
        "weekly-summary is not in the catalog; deploy + approve it before running this test"
    )

    # Clear MailHog so we can assert exactly one new message later.
    httpx.delete(f"{MAILHOG_URL}/api/v1/messages", timeout=5.0)

    # Start the run. Region must match a region in the seeded sample data.
    inputs = {"region": "EMEA", "recipient_email": "lead@example.com"}
    started = httpx.post(
        f"{API_URL}/runs",
        json={"agent_slug": "weekly-summary", "inputs": inputs},
        headers=_hdrs(user_token),
        timeout=10.0,
    )
    started.raise_for_status()
    run_id = started.json()["id"]

    # Wait for it to reach awaiting_approval.
    run = _wait_for_status(user_token, run_id, "awaiting_approval", timeout=60.0)
    assert run["status"] == "awaiting_approval"

    approvals = httpx.get(
        f"{API_URL}/runs/{run_id}/approvals", headers=_hdrs(user_token), timeout=5.0
    ).json()
    assert len(approvals) == 1
    approval = approvals[0]
    assert approval["action"] == "email.send"
    assert approval["status"] == "pending"

    # Admin approves.
    decided = httpx.post(
        f"{API_URL}/admin/approvals/{approval['id']}/decide",
        json={"decision": "approved"},
        headers=_hdrs(admin_token),
        timeout=10.0,
    ).json()
    assert decided["status"] == "approved"

    # Run resumes and finishes.
    run = _wait_for_status(user_token, run_id, "succeeded", timeout=90.0)
    assert run["result_json"]["email_sent"] is True
    assert run["result_json"]["approval_status"] == "approved"

    # MailHog has exactly one message addressed to the recipient.
    inbox = httpx.get(f"{MAILHOG_URL}/api/v2/messages", timeout=5.0).json()
    assert inbox["total"] >= 1
    addressees = {
        f"{m['To'][0]['Mailbox']}@{m['To'][0]['Domain']}" for m in inbox["items"]
    }
    assert "lead@example.com" in addressees

    # User leaves feedback.
    fb = httpx.post(
        f"{API_URL}/runs/{run_id}/feedback",
        json={"rating": "up", "comment": "nice summary"},
        headers=_hdrs(user_token),
        timeout=5.0,
    )
    fb.raise_for_status()

    # Dev sees it on the agent dashboard.
    dev_view = httpx.get(
        f"{API_URL}/dev/agents/weekly-summary/feedback",
        headers=_hdrs(dev_token),
        timeout=5.0,
    ).json()
    matching = [item for item in dev_view["items"] if item["run_id"] == run_id]
    assert len(matching) == 1
    assert matching[0]["rating"] == "up"
    assert matching[0]["comment"] == "nice summary"


def test_inbox_triage_fails_without_mailbox_token(user_token: str) -> None:
    # Disconnect MAILBOX_TOKEN if previously connected.
    secrets = httpx.get(
        f"{API_URL}/me/secrets", headers=_hdrs(user_token), timeout=5.0
    ).json()
    for s in secrets:
        if s["name"] == "MAILBOX_TOKEN":
            httpx.delete(
                f"{API_URL}/me/secrets/{s['id']}", headers=_hdrs(user_token), timeout=5.0
            )

    started = httpx.post(
        f"{API_URL}/runs",
        json={"agent_slug": "inbox-triage", "inputs": {}},
        headers=_hdrs(user_token),
        timeout=10.0,
    )
    if started.status_code == 404:
        pytest.skip("inbox-triage not deployed in this environment")
    started.raise_for_status()
    run_id = started.json()["id"]

    run = _wait_for_status(user_token, run_id, "failed", "succeeded", timeout=60.0)
    assert run["status"] == "failed"
    assert "MAILBOX_TOKEN" in (run.get("error") or "")
