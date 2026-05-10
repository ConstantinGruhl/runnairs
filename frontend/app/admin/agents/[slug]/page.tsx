"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ConnectionList } from "@/components/ConnectionList";
import { InstallationReadinessCard } from "@/components/InstallationReadinessCard";
import { ModuleActivationCard } from "@/components/ModuleActivationCard";
import { Badge, Card } from "@/components/ui";
import { ApiError, apiFetch } from "@/lib/api";
import type { AgentInstallationDetail, ConnectionRecord, InstallationSummary, ModuleSpec } from "@/lib/types";

interface AgentVersion {
  id: string;
  version: string;
  image_tag: string | null;
  descriptor_format: string;
  inspection: Record<string, unknown> | null;
  created_at: string;
  approved_at: string | null;
  is_current: boolean;
}

interface AdminAgentDetail {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  status: string;
  current_version_id: string | null;
  modules: ModuleSpec[];
  installation: InstallationSummary | null;
  versions: AgentVersion[];
}

export default function AdminAgentInstallationPage() {
  const params = useParams<{ slug: string }>();
  const [agent, setAgent] = useState<AdminAgentDetail | null>(null);
  const [installation, setInstallation] = useState<AgentInstallationDetail | null>(null);
  const [connections, setConnections] = useState<ConnectionRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyModule, setBusyModule] = useState<string | null>(null);

  async function refresh() {
    try {
      const [agentData, installationData, connectionData] = await Promise.all([
        apiFetch<AdminAgentDetail>(`/dev/agents/${params.slug}`),
        apiFetch<AgentInstallationDetail>(`/admin/agents/${params.slug}/installation`),
        apiFetch<ConnectionRecord[]>("/admin/connections"),
      ]);
      setAgent(agentData);
      setInstallation(installationData);
      setConnections(connectionData);
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : String(e));
    }
  }

  useEffect(() => {
    refresh();
  }, [params.slug]);

  async function toggleModule(moduleId: string) {
    if (!installation) return;
    setBusyModule(moduleId);
    setError(null);
    const enabled = new Set(installation.enabled_modules);
    if (enabled.has(moduleId)) {
      enabled.delete(moduleId);
    } else {
      enabled.add(moduleId);
    }
    try {
      const next = await apiFetch<AgentInstallationDetail>(`/admin/agents/${params.slug}/installation`, {
        method: "PUT",
        body: JSON.stringify({
          enabled_modules: Array.from(enabled),
          config: installation.config,
        }),
      });
      setInstallation(next);
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : String(e));
    } finally {
      setBusyModule(null);
      await refresh();
    }
  }

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (agent === null || installation === null) {
    return <p className="text-sm text-muted-foreground">Loading...</p>;
  }

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <Link href="/admin/agents" className="text-xs text-muted-foreground hover:underline">
          ← back to agents
        </Link>
        <div className="flex items-center gap-2 mt-2">
          <h1 className="text-2xl font-semibold">{agent.name}</h1>
          <Badge tone={agent.status === "approved" ? "green" : agent.status === "draft" ? "amber" : "gray"}>
            {agent.status}
          </Badge>
          <Badge tone={installation.ready ? "green" : "amber"}>{installation.status}</Badge>
        </div>
        <p className="text-xs text-muted-foreground mt-1">{agent.slug}</p>
      </div>

      <InstallationReadinessCard
        ready={installation.ready}
        missingWorkspaceConnections={installation.missing_workspace_connections}
        missingUserConnections={installation.missing_user_connections}
        disabledRequiredModules={installation.disabled_required_modules}
      />

      <ModuleActivationCard
        modules={installation.modules}
        enabledModules={installation.enabled_modules}
        editable={busyModule === null}
        onToggle={toggleModule}
      />

      <ConnectionList connections={connections} />

      <Card>
        <h2 className="text-base font-medium mb-3">Versions</h2>
        <ul className="divide-y divide-border">
          {agent.versions.map((version) => (
            <li key={version.id} className="py-2.5 flex items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm">{version.version}</span>
                  {version.is_current && <Badge tone="green">current</Badge>}
                  <Badge tone="blue">{version.descriptor_format}</Badge>
                </div>
                <p className="text-xs text-muted-foreground mt-1 font-mono">{version.image_tag}</p>
              </div>
              <span className="text-xs text-muted-foreground">
                {new Date(version.created_at).toLocaleString()}
              </span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
