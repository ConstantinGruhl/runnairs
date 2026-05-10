"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ConnectedAccounts } from "@/components/ConnectedAccounts";
import { InstallationReadinessCard } from "@/components/InstallationReadinessCard";
import { ModuleActivationCard } from "@/components/ModuleActivationCard";
import { RunStatusBadge } from "@/components/RunStatus";
import { Badge, Button, Card, Input, Label } from "@/components/ui";
import { ApiError, apiFetch } from "@/lib/api";
import type { CatalogDetail, Run } from "@/lib/types";

export default function AgentDetailPage() {
  const params = useParams<{ slug: string }>();
  const router = useRouter();

  const [agent, setAgent] = useState<CatalogDetail | null>(null);
  const [recentRuns, setRecentRuns] = useState<Run[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  async function loadAgent() {
    const data = await apiFetch<CatalogDetail>(`/app/catalog/${params.slug}`);
    setAgent(data);
    const initial: Record<string, string> = {};
    for (const name of Object.keys(data.inputs ?? {})) {
      initial[name] = formValues[name] ?? "";
    }
    setFormValues(initial);
  }

  useEffect(() => {
    loadAgent().catch((e) =>
      setLoadError(e instanceof ApiError ? String(e.detail) : String(e)),
    );

    apiFetch<Run[]>(`/runs?agent_slug=${params.slug}&limit=5`)
      .then(setRecentRuns)
      .catch(() => setRecentRuns([]));
  }, [params.slug]);

  if (loadError) {
    return <p className="text-sm text-red-600">{loadError}</p>;
  }
  if (agent === null) {
    return <p className="text-sm text-muted-foreground">Loading...</p>;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const currentAgent = agent;
    if (!currentAgent) return;
    setSubmitting(true);
    setSubmitError(null);
    const inputs: Record<string, string> = {};
    for (const [name, val] of Object.entries(formValues)) {
      if (val !== "") inputs[name] = val;
    }
    try {
      const run = await apiFetch<Run>("/runs", {
        method: "POST",
        body: JSON.stringify({ agent_slug: currentAgent.slug, inputs }),
      });
      router.push(`/app/runs/${run.id}`);
    } catch (e) {
      setSubmitError(e instanceof ApiError ? String(e.detail) : String(e));
      setSubmitting(false);
    }
  }

  const inputEntries = Object.entries(agent.inputs);

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <Link href="/app" className="text-xs text-muted-foreground hover:underline">
          ← back to catalog
        </Link>
        <h1 className="text-2xl font-semibold mt-2">{agent.name}</h1>
        <p className="text-xs text-muted-foreground">
          {agent.slug} · {agent.version}
        </p>
        {agent.description && (
          <p className="text-sm mt-3 whitespace-pre-line">{agent.description}</p>
        )}
      </div>

      <Card className="space-y-3">
        <div className="text-sm font-medium">Permissions</div>
        <div className="space-y-1.5">
          <div className="text-xs text-muted-foreground">Tools this automation can call</div>
          <div className="flex flex-wrap gap-1">
            {agent.tools.map((tool) => (
              <Badge key={tool}>{tool}</Badge>
            ))}
            {agent.tools.length === 0 && (
              <span className="text-xs text-muted-foreground">(none)</span>
            )}
          </div>
        </div>
        {agent.approvals_required_for.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-xs text-muted-foreground">Requires your approval before</div>
            <div className="flex flex-wrap gap-1">
              {agent.approvals_required_for.map((approval) => (
                <Badge key={approval} tone="amber">
                  {approval}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </Card>

      <InstallationReadinessCard
        ready={agent.installation.ready}
        missingWorkspaceConnections={agent.installation.missing_workspace_connections}
        missingUserConnections={agent.installation.missing_user_connections}
        disabledRequiredModules={agent.installation.disabled_required_modules}
      />

      <ModuleActivationCard
        modules={agent.modules}
        enabledModules={agent.installation.enabled_modules}
        editable={false}
      />

      {agent.user_secrets_needed.length > 0 && (
        <ConnectedAccounts required={agent.user_secrets_needed} onChange={loadAgent} />
      )}

      <Card className="space-y-4">
        <h2 className="text-base font-medium">Run this automation</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          {inputEntries.length === 0 && (
            <p className="text-sm text-muted-foreground">No inputs required.</p>
          )}
          {inputEntries.map(([name, spec]) => (
            <div key={name} className="space-y-1.5">
              <Label htmlFor={`in-${name}`}>
                {name}
                {spec.required && <span className="text-red-600">*</span>}
                <span className="text-xs text-muted-foreground ml-2">{spec.type ?? "string"}</span>
              </Label>
              <Input
                id={`in-${name}`}
                required={spec.required}
                value={formValues[name] ?? ""}
                onChange={(e) =>
                  setFormValues((prev) => ({ ...prev, [name]: e.target.value }))
                }
              />
              {spec.description && (
                <p className="text-xs text-muted-foreground">{spec.description}</p>
              )}
            </div>
          ))}
          {submitError && <p className="text-sm text-red-600">{submitError}</p>}
          {agent.installation.disabled_required_modules.length > 0 && (
            <p className="text-sm text-amber-700">
              An admin needs to re-enable the required modules before this automation can run.
            </p>
          )}
          <Button
            type="submit"
            disabled={submitting || agent.installation.disabled_required_modules.length > 0}
          >
            {submitting ? "Starting..." : "Run"}
          </Button>
        </form>
      </Card>

      {recentRuns.length > 0 && (
        <Card>
          <h2 className="text-base font-medium mb-3">Your recent runs</h2>
          <ul className="divide-y divide-border">
            {recentRuns.map((run) => (
              <li key={run.id} className="py-2.5 flex items-center justify-between gap-3">
                <Link
                  href={`/app/runs/${run.id}`}
                  className="text-sm font-mono hover:underline truncate"
                >
                  {run.id.slice(0, 8)}...
                </Link>
                <RunStatusBadge status={run.status} />
                <span className="text-xs text-muted-foreground">
                  {run.started_at ? new Date(run.started_at).toLocaleString() : "—"}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
