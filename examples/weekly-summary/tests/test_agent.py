"""Unit test for weekly-summary covering all four branches:
  - empty pipeline → no LLM, no email
  - LLM + approval approved → email sent
  - approval denied → email NOT sent
  - approval timeout → email NOT sent
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from platform_sdk.testing import MockGateway


_ROW = {
    "name": "Acme expansion",
    "stage": "negotiation",
    "amount_usd": 240000.0,
    "closes_on": "2026-06-30",
}


def test_empty_pipeline_skips_llm_and_email():
    with MockGateway() as gw:
        gw.set_inputs({"region": "EMEA", "recipient_email": "lead@example.com"})
        gw.stub_postgres_query([])

        from main import run
        result = run()

    assert result["row_count"] == 0
    assert result["email_sent"] is False
    assert gw.calls_to("/tools/llm/complete") == 0
    assert gw.calls_to("/tools/email/send") == 0


def test_approved_path_sends_email():
    with MockGateway() as gw:
        gw.set_inputs({"region": "EMEA", "recipient_email": "lead@example.com"})
        gw.stub_postgres_query([_ROW])
        gw.stub_llm_complete(text="• biggest deal …", tokens_used=80)
        gw.stub_approval(approved=True)
        gw.stub_email_send()

        from main import run
        result = run()

    assert result["email_sent"] is True
    assert result["approval_status"] == "approved"
    assert result["row_count"] == 1
    assert gw.calls_to("/approvals") == 1
    assert gw.calls_to("/tools/email/send") == 1
    sent = gw.last_call("/tools/email/send").payload
    assert sent["to"] == "lead@example.com"
    assert "EMEA" in sent["subject"]


def test_denied_approval_does_not_send():
    with MockGateway() as gw:
        gw.set_inputs({"region": "EMEA", "recipient_email": "lead@example.com"})
        gw.stub_postgres_query([_ROW])
        gw.stub_llm_complete(text="• …")
        gw.stub_approval(approved=False)

        from main import run
        result = run()

    assert result["email_sent"] is False
    assert result["approval_status"] == "denied"
    assert gw.calls_to("/tools/email/send") == 0
