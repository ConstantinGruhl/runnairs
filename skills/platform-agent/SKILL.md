---
name: platform-agent
description: Use this skill when building, modifying, or reviewing an automation package for the Enterprise AI Agent Platform. Triggers when you see an automation.yaml or agent.yaml plus main.py, when the user asks to "write an agent that …" or "add a tool to my agent", or when working inside any directory under examples/ in this repo. Covers the package contract, the SDK surface, the platform's invariants, the deploy flow, and a pre-deploy checklist.
---

# platform-agent skill

You are helping write code for an enterprise AI agent platform. Agents are
short-lived Python programs that run in isolated containers, call platform
tools through a thin SDK, and never reach the network or the database
directly.

If you take only one thing from this document: **agents go through the
platform for everything**. No `import requests`. No `os.environ["API_KEY"]`.
No raw SQL connections. The SDK is the only allowed surface.

## When to use this skill

Trigger when:

- You see a directory containing `automation.yaml` or `agent.yaml` and `main.py`.
- The user asks to write, modify, or review a platform agent
  ("build an agent that…", "add a tool to my agent", "why does my agent
  fail to deploy", etc.).
- You are working inside any path under `examples/` in this repository.

## Agent contract

A native automation package should start with `automation.yaml`.
Use `agent.yaml` only when maintaining a compatibility package that has not migrated yet.

A deployed agent is a directory with these core files:

```
my-agent/
  agent.yaml      # manifest — declares everything the agent needs
  main.py         # one entry point function: run() -> dict
  requirements.txt  # optional, extra Python deps beyond what the runtime ships
```

### `agent.yaml`

```yaml
name: my-agent                  # slug: ^[a-z][a-z0-9-]{0,62}$
display_name: Friendly name shown in the catalog
description: |
  One-paragraph "what does this do" for the user catalog card.
runtime: python3.12             # only python3.12 is supported today
entrypoint: main:run            # module:function

inputs:                         # generated into a form on the agent page
  region:
    type: string
    required: true
  recipient_email:
    type: string
    required: false

permissions:
  tools:                        # MUST list every tool the agent calls
    - llm.complete
    - email.send
    - postgres.query
  secrets:                      # MUST list every secret resolved by name
    - name: OPENAI_API_KEY
      scope: workspace          # workspace OR user
    - name: MAILBOX_TOKEN
      scope: user               # resolved per triggering user
  http_allowlist:               # required if tools includes http.request
    - https://api.hubspot.com/*
    - https://*.atlassian.net/*

approvals:
  required_for:                 # tool calls that must be human-approved
    - email.send

schedule:                       # optional; managed in the UI for prototype
  cron: "0 9 * * MON"
  timezone: "Europe/Berlin"

limits:                         # hard caps; platform enforces these
  timeout_seconds: 300
  memory_mb: 512
  max_tokens: 50000
  max_cost_usd: 1.00
```

### `main.py`

The entrypoint takes no arguments. Inputs are read off `ctx.inputs`. The
return value must be a JSON-serializable dict — the platform stores it as
`run.result_json` and shows it on the run detail page.

```python
from platform_sdk import ctx, tools

def run() -> dict:
    region = ctx.inputs["region"]
    rows = tools.postgres.query(
        "SELECT name, amount_usd FROM opportunities WHERE region = :region",
        {"region": region},
    )
    summary = tools.llm.complete(
        model="gpt-4o-mini",
        prompt=f"Summarize for leadership: {rows}",
    )
    approval = ctx.request_approval(
        action="email.send",
        title="Send the summary email?",
        body=summary.text,
    )
    if approval.approved:
        tools.email.send(
            to=ctx.inputs["recipient_email"],
            subject=f"Weekly Summary — {region}",
            body=summary.text,
        )
        return {"summary": summary.text, "email_sent": True}
    return {"summary": summary.text, "email_sent": False}
```

## SDK surface (everything you may import)

```python
from platform_sdk import ctx, tools
```

### `ctx`

| Name | Type | What it does |
|---|---|---|
| `ctx.run_id` | `uuid.UUID` | The run the agent is executing for. |
| `ctx.inputs` | `dict[str, Any]` | The inputs the user (or scheduler) submitted. |
| `ctx.log(msg, level="info")` | `None` | Emit a line that the platform captures. |
| `ctx.request_approval(action, title, body=None, payload=None, timeout_seconds=1800)` | `Approval` | Pause the run, ask a human, return `Approval(approved, status, decided_by, decided_at)`. |

### `tools.llm`

```python
result = tools.llm.complete(
    model="gpt-4o-mini",                  # OpenAI chat-completion model
    prompt="...",                          # required
    system="optional system prompt",
    temperature=0.0,
    max_tokens=400,
)
result.text          # str
result.tokens_used   # int
result.cost_usd      # float (estimate)
result.backend       # "openai" | "stub" — falls back to deterministic stub
                     # when no OPENAI_API_KEY is configured for the tenant
```

### `tools.email`

```python
tools.email.send(to="alice@example.com", subject="hi", body="...")
# returns SendResult(ok=True, backend="smtp")
```

If the agent declares `email.send` in `approvals.required_for`, the gateway
rejects the call until an approval has been granted for the action
`"email.send"` on this run. **Always** call `ctx.request_approval(action="email.send", ...)`
before `tools.email.send` for approval-gated agents.

### `tools.postgres`

```python
rows = tools.postgres.query(
    "SELECT * FROM opportunities WHERE region = :region",
    {"region": "EMEA"},
)
# rows is a list[dict]; reads only — INSERT/UPDATE/DELETE/DDL is rejected
```

### `tools.http`

```python
res = tools.http.get("https://api.hubspot.com/contacts/v1/lists")
res = tools.http.post("https://example.com/webhook", json={"x": 1})
res = tools.http.request("PUT", url, headers={"X-Foo": "bar"}, body="raw")
res.status_code    # int
res.body           # str
res.headers        # dict[str, str]
res.json()         # parsed body
```

The URL **must** match one of the patterns in `permissions.http_allowlist`.
Patterns are simple globs: `https://*.atlassian.net/*` matches any subdomain
and any path; `https://api.example.com/v2/*` matches any path under
`/v2/` on that host.

### `tools.inbox`

```python
emails = tools.inbox.list_emails()
# list[dict] with from / subject / body / received_at
# requires user-scope MAILBOX_TOKEN
```

## Platform invariants — never violate

These are non-negotiable rules. If a user request would violate one, push
back before writing code.

1. **No raw secrets.** Never read `os.environ["FOO_API_KEY"]`. Always use
   `tools.<surface>` (the gateway resolves secrets internally) or, when
   you genuinely need the value yourself, wrap it via the platform — never
   bypass.
2. **No direct external HTTP.** No `import requests`, no `urllib.request`,
   no `httpx.get(...)`. All HTTP egress goes through `tools.http.request`
   and is bound by `permissions.http_allowlist`.
3. **No raw DB connections.** No `psycopg`, `sqlalchemy.create_engine`, or
   similar. Use `tools.postgres.query`.
4. **Every tool you call must be in `permissions.tools`.** Adding a tool
   call without declaring it is a deploy-time validation error and a
   gateway-level 403 at run time.
5. **Every secret you resolve must be in `permissions.secrets`** with the
   correct `scope` (workspace or user).
6. **Approval-gated tools require an approval.** If the agent has
   `approvals.required_for: [email.send]`, the agent must call
   `ctx.request_approval(action="email.send", ...)` and check
   `approval.approved` before calling `tools.email.send`.

## Pre-deploy checklist

Before declaring an agent "done", walk through this list. Stop at the
first thing that fails and fix it.

- [ ] `agent.yaml` parses and has `name`, `entrypoint`, and a non-empty
      `permissions.tools`.
- [ ] `name` is a valid slug: `^[a-z][a-z0-9-]{0,62}$`.
- [ ] `entrypoint` is `module:function` and the function is callable in
      `main.py`.
- [ ] Every tool the code calls is in `permissions.tools`.
      ```bash
      grep -E "tools\.(llm|email|postgres|http|inbox)\.[a-z_]+" main.py
      ```
- [ ] Every secret name passed to a tool that resolves secrets is in
      `permissions.secrets`, with the right scope (workspace if it's a
      tenant-level credential, user if it's per-end-user).
- [ ] If `tools.http.request` (or `.get`/`.post`) is called,
      `permissions.http_allowlist` is non-empty AND every URL the agent
      hits matches at least one pattern.
- [ ] If any tool call has irreversible side effects (sending email,
      writing externally), it is listed in `approvals.required_for` AND
      preceded in code by `ctx.request_approval(action="<that-tool>", …)`.
- [ ] **Forbidden imports check** in `main.py`:
      ```bash
      grep -nE "^\s*(import|from)\s+(requests|urllib|http\.client|psycopg|sqlalchemy|smtplib)" main.py
      ```
      should return nothing.
- [ ] `os.environ` is used only for things the runtime injects
      (`RUN_ID`, `RUN_TOKEN`, `TOOL_GATEWAY_URL`, `RUN_INPUTS`) — never
      for secret values.
- [ ] `tests/test_agent.py` exists and uses `platform_sdk.testing`
      (see below). At least one test that hits the happy path.
- [ ] `limits.timeout_seconds`, `limits.max_tokens`, `limits.max_cost_usd`
      are set to reasonable values for the workload.

## Testing — `platform_sdk.testing`

Each agent ships a unit test that runs `main:run` against a mocked
gateway. Use `MockGateway` to capture calls and stub responses:

```python
# my-agent/tests/test_agent.py
from platform_sdk.testing import MockGateway

def test_happy_path():
    with MockGateway() as gw:
        gw.set_inputs({"region": "EMEA", "recipient_email": "a@b.com"})
        gw.stub_llm_complete(text="• one\n• two\n• three")
        gw.stub_postgres_query([{"name": "Acme", "amount_usd": 100}])
        gw.stub_approval(approved=True)
        gw.stub_email_send()

        from main import run
        result = run()

    assert result["email_sent"] is True
    assert "Acme" not in result["summary"]  # we only sent the LLM output
    # Each call is captured and assertable:
    assert gw.calls_to("/tools/email/send") == 1
```

`MockGateway` patches `platform_sdk._client.post`, so any tool surface
goes through it. It also sets `RUN_ID`, `RUN_TOKEN`, and
`TOOL_GATEWAY_URL` to dummy values so the SDK is happy.

## Deploying

```bash
pip install -e packages/platform_cli   # one-time
platform-cli login --email dev@demo.local --api-url http://localhost:8000
platform-cli deploy ./my-agent
```

The CLI zips the directory, uploads to the control plane, which validates
the manifest, builds an image tagged `agent-<uuid>:v<n>` from
`platform/agent-runtime` plus the agent code, and creates a draft
`AgentVersion`. An admin must approve the version before end users can
run it.

## Worked examples

The four agents under `examples/` are the canonical references — read
them when stuck:

- **`hello-world`** — single `tools.llm.complete` call. Smallest possible
  agent.
- **`weekly-summary`** — postgres + LLM + approval + email. The pause-and-
  approve flow.
- **`inbox-triage`** — user-scope `MAILBOX_TOKEN`, demonstrates failing
  cleanly when an end user hasn't connected their account.
- **`customer-briefing`** — postgres + http with `http_allowlist` against
  the in-cluster mock CRM. Shows how to compose internal data with
  external APIs.

When the user asks "build me an agent that does X", read the closest
example first, copy its layout, and adapt.
