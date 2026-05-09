"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { RunStatusBadge } from "@/components/RunStatus";
import { Card } from "@/components/ui";
import { ApiError, apiFetch } from "@/lib/api";
import type { Run } from "@/lib/types";

export default function MyRunsPage() {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<Run[]>("/runs?limit=100")
      .then(setRuns)
      .catch((e) => setError(e instanceof ApiError ? String(e.detail) : String(e)));
  }, []);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (runs === null) return <p className="text-sm text-muted-foreground">Loading…</p>;

  return (
    <div className="max-w-4xl space-y-4">
      <h1 className="text-2xl font-semibold">My runs</h1>
      {runs.length === 0 ? (
        <p className="text-sm text-muted-foreground">No runs yet.</p>
      ) : (
        <Card className="p-0 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-muted/30">
              <tr>
                <th className="text-left p-3">Agent</th>
                <th className="text-left p-3">Status</th>
                <th className="text-left p-3">Started</th>
                <th className="text-left p-3">Run id</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {runs.map((r) => (
                <tr key={r.id}>
                  <td className="p-3">
                    {r.agent_slug ? (
                      <Link href={`/app/agents/${r.agent_slug}`} className="hover:underline">
                        {r.agent_name ?? r.agent_slug}
                      </Link>
                    ) : (
                      <span className="text-muted-foreground">unknown</span>
                    )}
                  </td>
                  <td className="p-3"><RunStatusBadge status={r.status} /></td>
                  <td className="p-3 text-xs text-muted-foreground">
                    {r.started_at ? new Date(r.started_at).toLocaleString() : "—"}
                  </td>
                  <td className="p-3 text-xs">
                    <Link href={`/app/runs/${r.id}`} className="font-mono hover:underline">
                      {r.id.slice(0, 8)}…
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
