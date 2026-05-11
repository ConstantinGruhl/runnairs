"use client";

import { Badge, Card } from "@/components/ui";

const PURPOSE_POINTS = [
  "Admins manage workspace secrets, approvals, connections, and publication state.",
  "Developers package automations, deploy versions, inspect readiness, and monitor feedback.",
  "Users discover approved automations, connect required accounts, run them, and review outcomes.",
];

const FLOW_POINTS = [
  "A developer deploys an automation package and the platform builds an isolated runtime image.",
  "An admin approves a version and configures installation state such as secrets, connections, and schedules.",
  "A user launches a run, the control plane enqueues it, and the worker starts a locked-down container.",
  "The agent can only reach approved tools through the gateway, which enforces secrets, permissions, and approvals.",
  "Results, logs, approvals, feedback, and schedules stay attached to the workspace for later review.",
];

const OPERATIONS_POINTS = [
  "Use the Catalog area to understand what an automation needs before launching it.",
  "Use Admin secrets and connections to satisfy workspace-level requirements like LLM credentials.",
  "Use Admin users to manage built-in IAM accounts, roles, status, and one-time reset or recovery codes.",
  "Use Admin authentication to register an OIDC provider, map claims to roles, and switch the instance into hybrid or OIDC-only mode.",
  "Use Developer pages to inspect versions, schedules, installation readiness, and user feedback.",
  "For production, run the compose stack with the production overlay and set strong secrets before first launch.",
];

const SECURITY_POINTS = [
  "Run containers start with a read-only root filesystem, dropped capabilities, and an internal-only network.",
  "The tool gateway authorizes every tool call with a short-lived run token and per-tool permission checks.",
  "Approval-gated actions such as email sends remain blocked until an authorized admin approves them.",
  "Secrets are stored encrypted at rest and should be backed by strong environment secrets in production.",
  "Browser logins now rely on HttpOnly session cookies, and the bootstrap admin should store the offline recovery code outside the platform.",
];

export function PlatformDocs({
  audience,
}: {
  audience: "admin" | "developer" | "user";
}) {
  const startingPoint =
    audience === "admin"
      ? "Start with Secrets, Connections, and Agent approvals to make the workspace runnable."
      : audience === "developer"
        ? "Start with Agents and New Automation to package, deploy, and iterate on automations."
        : "Start with Catalog to see what is available and what accounts you need to connect.";

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-semibold">Documentation</h1>
          <Badge tone="blue">in-app guide</Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          Purpose, usage, security model, and operating guidance for the platform.
        </p>
      </div>

      <Card className="space-y-3">
        <div>
          <h2 className="text-base font-medium">What This Platform Is For</h2>
          <p className="text-sm text-muted-foreground mt-1">
            This platform hosts workspace-scoped AI automations that run inside isolated containers
            and access tools through a governed gateway.
          </p>
        </div>
        <ul className="space-y-2 text-sm text-muted-foreground">
          {PURPOSE_POINTS.map((point) => (
            <li key={point}>{point}</li>
          ))}
        </ul>
      </Card>

      <Card className="space-y-3">
        <div>
          <h2 className="text-base font-medium">How It Works</h2>
          <p className="text-sm text-muted-foreground mt-1">
            The platform separates packaging, approval, execution, and tool access so automations can
            be run safely and repeatedly.
          </p>
        </div>
        <ul className="space-y-2 text-sm text-muted-foreground">
          {FLOW_POINTS.map((point) => (
            <li key={point}>{point}</li>
          ))}
        </ul>
      </Card>

      <Card className="space-y-3">
        <div>
          <h2 className="text-base font-medium">Using The Product</h2>
          <p className="text-sm text-muted-foreground mt-1">{startingPoint}</p>
        </div>
        <ul className="space-y-2 text-sm text-muted-foreground">
          {OPERATIONS_POINTS.map((point) => (
            <li key={point}>{point}</li>
          ))}
        </ul>
      </Card>

      <Card className="space-y-3">
        <div>
          <h2 className="text-base font-medium">Security Model</h2>
          <p className="text-sm text-muted-foreground mt-1">
            The platform is built around isolation, explicit permissions, and human approval gates.
          </p>
        </div>
        <ul className="space-y-2 text-sm text-muted-foreground">
          {SECURITY_POINTS.map((point) => (
            <li key={point}>{point}</li>
          ))}
        </ul>
      </Card>

      <Card className="space-y-3">
        <div>
          <h2 className="text-base font-medium">Authentication Modes</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Built-in IAM is the default. After setup, an admin can register an OpenID Connect provider under
            Admin → Authentication and choose <span className="font-mono">hybrid</span> (both built-in and SSO)
            or <span className="font-mono">oidc</span> (SSO-only, with the bootstrap admin retaining built-in
            credentials as a break-glass account). Removing the provider while the instance is in hybrid or
            OIDC mode demotes the mode back to built-in.
          </p>
        </div>
      </Card>

      <Card className="space-y-3">
        <div>
          <h2 className="text-base font-medium">Current Production Focus</h2>
          <p className="text-sm text-muted-foreground mt-1">
            The current production baseline includes secure first-run setup, built-in IAM, and an OpenID
            Connect integration with claim-to-role mapping. The next milestones are Git-backed skill
            distribution, stronger CI and security testing, and broader operational hardening for self-hosting.
          </p>
        </div>
      </Card>
    </div>
  );
}
