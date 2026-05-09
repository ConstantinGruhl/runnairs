"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

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

  useEffect(() => {
    apiFetch<CatalogDetail>(`/app/catalog/${params.slug}`)
      .then((d) => {
        setAgent(d);
        const initial: Record<string, string> = {};
        for (const name of Object.keys(d.inputs ?? {})) {
          initial[name] = "";
        }
        setFormValues(initial);
      })
      .catch((e) =>
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
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!agent) return;
    setSubmitting(true);
    setSubmitError(null);
    const inputs: Record<string, string> = {};
    for (const [name, val] of Object.entries(formValues)) {
      if (val !== "") inputs[name] = val;
    }
    try {
      const run = await apiFetch<Run>("/runs", {
        method: "POST",
        body: JSON.stringify({ agent_slug: agent.slug, inputs }),
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
        <p className="text-xs text-muted-foreground">{agent.slug} · {agent.version}</p>
        {agent.description && (
          <p className="text-sm mt-3 whitespace-pre-line">{agent.description}</p>
        )}
      </div>

      <Card className="space-y-3">
        <div className="text-sm font-medium">Permissions</div>
        <div className="space-y-1.5">
          <div className="text-xs text-muted-foreground">Tools this agent can call</div>
          <div className="flex flex-wrap gap-1">
            {agent.tools.map((t) => (
              <Badge key={t}>{t}</Badge>
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
              {agent.approvals_required_for.map((a) => (
                <Badge key={a} tone="amber">{a}</Badge>
              ))}
            </div>
          </div>
        )}
        {agent.user_secrets_needed.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-xs text-muted-foreground">User-scope secrets needed</div>
            <div className="flex flex-wrap gap-1">
              {agent.user_secrets_needed.map((s) => (
                <Badge key={s.name} tone="blue">{s.name}</Badge>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              These are connected per user in Phase 8.
            </p>
          </div>
        )}
      </Card>

      <Card className="space-y-4">
        <h2 className="text-base font-medium">Run this agent</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          {inputEntries.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No inputs required.
            </p>
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
          {submitError && (
            <p className="text-sm text-red-600">{submitError}</p>
          )}
          <Button type="submit" disabled={submitting}>
            {submitting ? "Starting…" : "Run"}
          </Button>
        </form>
      </Card>

      {recentRuns.length > 0 && (
        <Card>
          <h2 className="text-base font-medium mb-3">Your recent runs</h2>
          <ul className="divide-y divide-border">
            {recentRuns.map((r) => (
              <li key={r.id} className="py-2.5 flex items-center justify-between gap-3">
                <Link
                  href={`/app/runs/${r.id}`}
                  className="text-sm font-mono hover:underline truncate"
                >
                  {r.id.slice(0, 8)}…
                </Link>
                <RunStatusBadge status={r.status} />
                <span className="text-xs text-muted-foreground">
                  {r.started_at ? new Date(r.started_at).toLocaleString() : "—"}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

