"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge, Card } from "@/components/ui";
import { ApiError, apiFetch } from "@/lib/api";
import type { AgentSummary } from "@/lib/types";

export default function DevHome() {
  const [agents, setAgents] = useState<AgentSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<{ agents: AgentSummary[] }>("/dev/agents")
      .then((r) => setAgents(r.agents))
      .catch((e) => setError(e instanceof ApiError ? String(e.detail) : String(e)));
  }, []);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (agents === null) return <p className="text-sm text-muted-foreground">Loading…</p>;

  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Your agents</h1>
        <p className="text-sm text-muted-foreground">
          Deploy new versions with <code className="font-mono text-xs">platform-cli deploy ./your-agent</code>.
          Admins approve drafts before they appear in the catalog.
        </p>
      </div>

      {agents.length === 0 ? (
        <Card>
          <p className="text-sm text-muted-foreground">
            No agents yet. Try{" "}
            <code className="font-mono text-xs">platform-cli init my-agent</code>.
          </p>
        </Card>
      ) : (
        <div className="space-y-2">
          {agents.map((a) => (
            <Link
              key={a.id}
              href={`/dev/agents/${a.slug}`}
              className="block"
            >
              <Card className="hover:border-primary/40 transition cursor-pointer">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-medium">{a.name}</h3>
                      <Badge tone={a.status === "approved" ? "green" : a.status === "draft" ? "amber" : "gray"}>
                        {a.status}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      {a.slug} · {a.version_count} {a.version_count === 1 ? "version" : "versions"}
                    </p>
                    {a.description && (
                      <p className="text-sm text-muted-foreground mt-2 line-clamp-2">
                        {a.description}
                      </p>
                    )}
                  </div>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}

      <Card className="text-xs text-muted-foreground space-y-1">
        <p className="font-medium text-foreground">Deploy from a terminal</p>
        <p>1. <code className="font-mono">pip install -e packages/platform_cli</code></p>
        <p>2. <code className="font-mono">platform-cli login --email dev@demo.local</code></p>
        <p>3. <code className="font-mono">platform-cli deploy ./examples/your-agent</code></p>
      </Card>
    </div>
  );
}
