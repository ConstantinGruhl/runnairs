"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { RunStatusBadge } from "@/components/RunStatus";
import { Badge, Card } from "@/components/ui";
import { ApiError, apiFetch } from "@/lib/api";
import type { Run } from "@/lib/types";

interface AgentVersion {
  id: string;
  version: string;
  image_tag: string | null;
  created_at: string;
  approved_at: string | null;
  is_current: boolean;
}

interface AgentDetail {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  status: string;
  current_version_id: string | null;
  versions: AgentVersion[];
}

export default function DevAgentDetail() {
  const params = useParams<{ slug: string }>();
  const [agent, setAgent] = useState<AgentDetail | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<AgentDetail>(`/dev/agents/${params.slug}`)
      .then(setAgent)
      .catch((e) => setError(e instanceof ApiError ? String(e.detail) : String(e)));
    apiFetch<Run[]>(`/runs?agent_slug=${params.slug}&limit=20`)
      .then(setRuns)
      .catch(() => setRuns([]));
  }, [params.slug]);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (agent === null) return <p className="text-sm text-muted-foreground">Loading…</p>;

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <Link href="/dev" className="text-xs text-muted-foreground hover:underline">
          ← back to agents
        </Link>
        <div className="flex items-center gap-2 mt-2">
          <h1 className="text-2xl font-semibold">{agent.name}</h1>
          <Badge tone={agent.status === "approved" ? "green" : agent.status === "draft" ? "amber" : "gray"}>
            {agent.status}
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground mt-1">{agent.slug}</p>
        {agent.description && (
          <p className="text-sm mt-3 whitespace-pre-line">{agent.description}</p>
        )}
      </div>

      <Card>
        <h2 className="text-base font-medium mb-3">Versions</h2>
        <ul className="divide-y divide-border">
          {agent.versions.map((v) => (
            <li key={v.id} className="py-2.5 flex items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm">{v.version}</span>
                  {v.is_current && <Badge tone="green">current</Badge>}
                  {v.approved_at && <Badge tone="muted">approved</Badge>}
                </div>
                <p className="text-xs text-muted-foreground mt-0.5 font-mono">{v.image_tag}</p>
              </div>
              <span className="text-xs text-muted-foreground">
                {new Date(v.created_at).toLocaleString()}
              </span>
            </li>
          ))}
        </ul>
      </Card>

      <Card>
        <h2 className="text-base font-medium mb-3">Recent runs ({runs.length})</h2>
        {runs.length === 0 ? (
          <p className="text-sm text-muted-foreground">No runs yet.</p>
        ) : (
          <ul className="divide-y divide-border">
            {runs.map((r) => (
              <li key={r.id} className="py-2.5 flex items-center justify-between gap-3">
                <Link href={`/app/runs/${r.id}`} className="text-sm font-mono hover:underline">
                  {r.id.slice(0, 8)}…
                </Link>
                <RunStatusBadge status={r.status} />
                <span className="text-xs text-muted-foreground">
                  {r.started_at ? new Date(r.started_at).toLocaleString() : "—"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
