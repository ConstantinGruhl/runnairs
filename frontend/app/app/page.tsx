"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge, Card } from "@/components/ui";
import { ApiError, apiFetch } from "@/lib/api";
import type { CatalogEntry } from "@/lib/types";

export default function CatalogPage() {
  const [agents, setAgents] = useState<CatalogEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<{ agents: CatalogEntry[] }>("/app/catalog")
      .then((r) => setAgents(r.agents))
      .catch((e) => setError(e instanceof ApiError ? String(e.detail) : String(e)));
  }, []);

  if (error) {
    return <p className="text-sm text-red-600">{error}</p>;
  }
  if (agents === null) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (agents.length === 0) {
    return (
      <div className="space-y-3">
        <h1 className="text-2xl font-semibold">Catalog</h1>
        <p className="text-sm text-muted-foreground">
          No approved agents yet. Ask an admin to approve a deployed agent.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Catalog</h1>
        <p className="text-sm text-muted-foreground">
          {agents.length} approved {agents.length === 1 ? "agent" : "agents"} for your workspace.
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {agents.map((a) => (
          <AgentCard key={a.slug} agent={a} />
        ))}
      </div>
    </div>
  );
}

function AgentCard({ agent }: { agent: CatalogEntry }) {
  return (
    <Link href={`/app/agents/${agent.slug}`} className="block">
      <Card className="h-full hover:border-primary/40 transition cursor-pointer space-y-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <h3 className="font-medium">{agent.name}</h3>
            <p className="text-xs text-muted-foreground">{agent.slug} · {agent.version}</p>
          </div>
        </div>
        {agent.description && (
          <p className="text-sm text-muted-foreground line-clamp-3">
            {agent.description}
          </p>
        )}
        <div className="flex flex-wrap gap-1">
          {agent.tools.map((t) => (
            <Badge key={t} tone="muted">{t}</Badge>
          ))}
        </div>
        {agent.approvals_required_for.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {agent.approvals_required_for.map((a) => (
              <Badge key={a} tone="amber">approves: {a}</Badge>
            ))}
          </div>
        )}
        {agent.user_secrets_needed.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {agent.user_secrets_needed.map((s) => (
              <Badge key={s.name} tone="blue">connect: {s.name}</Badge>
            ))}
          </div>
        )}
      </Card>
    </Link>
  );
}

