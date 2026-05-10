"use client";

import { useEffect, useState } from "react";

import { ConnectionList } from "@/components/ConnectionList";
import { Badge, Button, Card, Input, Label } from "@/components/ui";
import { ApiError, apiFetch } from "@/lib/api";
import type { ConnectionRecord } from "@/lib/types";

export default function AdminConnectionsPage() {
  const [connections, setConnections] = useState<ConnectionRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [keyName, setKeyName] = useState("OPENAI_API_KEY");
  const [providerKey, setProviderKey] = useState("openai");
  const [displayName, setDisplayName] = useState("OpenAI");

  async function refresh() {
    try {
      setConnections(await apiFetch<ConnectionRecord[]>("/admin/connections"));
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : String(e));
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function createConnection(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await apiFetch("/admin/connections", {
        method: "POST",
        body: JSON.stringify({
          key: keyName,
          provider_key: providerKey,
          display_name: displayName,
        }),
      });
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex items-center gap-2">
        <h1 className="text-2xl font-semibold">Connections</h1>
        <Badge tone="blue">workspace</Badge>
      </div>
      <p className="text-sm text-muted-foreground">
        Track shared provider connections here. Use the Secrets page when you need to store the underlying credential value.
      </p>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <ConnectionList connections={connections ?? []} />
      <Card>
        <form onSubmit={createConnection} className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="conn-key">Key</Label>
              <Input id="conn-key" value={keyName} onChange={(e) => setKeyName(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="conn-provider">Provider</Label>
              <Input id="conn-provider" value={providerKey} onChange={(e) => setProviderKey(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="conn-name">Display name</Label>
              <Input id="conn-name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
            </div>
          </div>
          <Button type="submit" disabled={busy || !keyName || !providerKey}>
            {busy ? "Saving..." : "Add connection"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
