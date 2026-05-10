"""Unit test for the hello-world agent.

Run from the example dir with:

    PYTHONPATH=. pytest tests/

The MockGateway harness in platform_sdk.testing patches
platform_sdk._client.post so the agent never actually hits the network.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make `import main` work whether pytest is run from the agent dir or the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from platform_sdk.testing import MockGateway


def test_returns_llm_text():
    with MockGateway() as gw:
        gw.set_inputs({"greeting": "Hi"})
        gw.stub_llm_complete(text="Hi, agent platform!", tokens_used=12)

        from main import run
        result = run()

    assert result["text"] == "Hi, agent platform!"
    assert result["tokens"] == 12
    assert result["backend"] == "stub"
    # The greeting was passed through into the prompt
    last = gw.last_call("/tools/llm/complete")
    assert "Hi" in last.payload["prompt"]


def test_default_greeting():
    with MockGateway() as gw:
        gw.set_inputs({})
        gw.stub_llm_complete(text="Hello!")

        from main import run
        result = run()

    assert "Hello" in gw.last_call("/tools/llm/complete").payload["prompt"]
    assert result["text"] == "Hello!"
