"use client";

import { useEffect, useState } from "react";

import { Badge, Button, Card } from "@/components/ui";
import { ApiError, apiFetch } from "@/lib/api";
import type { PendingAgent } from "@/lib/types";

export default function AdminAgentsPage() {
  const [agents, setAgents] = useState<PendingAgent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState<string | null>(null);

  async function refresh() {
    setError(null);
    try {
      const r = await apiFetch<{ agents: PendingAgent[] }>("/admin/agents/pending");
      setAgents(r.agents);
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : String(e));
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function approve(slug: string) {
    setWorking(slug);
    setError(null);
    try {
      await apiFetch(`/admin/agents/${slug}/approve`, { method: "POST" });
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : String(e));
    } finally {
      setWorking(null);
    }
  }

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (agents === null) return <p className="text-sm text-muted-foreground">Loading…</p>;

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Agents</h1>
        <p className="text-sm text-muted-foreground">
          Approve agent versions for the catalog. End users can only run approved agents.
        </p>
      </div>

      {agents.length === 0 ? (
        <Card>
          <p className="text-sm text-muted-foreground">No agents in this workspace yet.</p>
        </Card>
      ) : (
        <div className="space-y-3">
          {agents.map((a) => {
            const tools = (((a.manifest as Record<string, unknown>).permissions as { tools?: string[] } | undefined)?.tools) ?? [];
            return (
              <Card key={a.agent_id} className="space-y-2.5">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-medium">{a.name}</h3>
                      <Badge tone={a.status === "approved" ? "green" : a.status === "draft" ? "amber" : "gray"}>
                        {a.status}
                      </Badge>
                      <Badge>{a.latest_version}</Badge>
                      {a.approved && <Badge tone="muted">version approved</Badge>}
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">{a.slug}</p>
                  </div>
                  <Button
                    variant={a.approved ? "secondary" : "primary"}
                    onClick={() => approve(a.slug)}
                    disabled={working === a.slug}
                  >
                    {working === a.slug ? "Approving…" : a.approved ? "Re-approve current" : "Approve"}
                  </Button>
                </div>
                {tools.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    <span className="text-xs text-muted-foreground self-center mr-1">tools:</span>
                    {tools.map((t) => (
                      <Badge key={t}>{t}</Badge>
                    ))}
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
