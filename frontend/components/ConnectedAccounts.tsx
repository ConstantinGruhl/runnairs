"use client";

import { useEffect, useState } from "react";

import { Badge, Button, Card, Input } from "@/components/ui";
import { ApiError, apiFetch } from "@/lib/api";
import type { WorkspaceSecret } from "@/lib/types";

interface UserSecretRequirement {
  name: string;
  scope: string;
}

export function ConnectedAccounts({
  required,
  onChange,
}: {
  required: UserSecretRequirement[];
  onChange?: () => void;
}) {
  const [connected, setConnected] = useState<WorkspaceSecret[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    try {
      setConnected(await apiFetch<WorkspaceSecret[]>("/me/secrets"));
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : String(e));
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function connect(name: string) {
    setBusy(true);
    setError(null);
    try {
      await apiFetch("/me/secrets", {
        method: "POST",
        body: JSON.stringify({ name, value: draft }),
      });
      setEditing(null);
      setDraft("");
      await refresh();
      onChange?.();
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function disconnect(secretId: string) {
    if (!confirm("Disconnect this account? Future runs that need it will fail.")) return;
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/me/secrets/${secretId}`, { method: "DELETE" });
      await refresh();
      onChange?.();
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (required.length === 0) return null;
  const byName = new Map((connected ?? []).map((c) => [c.name, c]));

  return (
    <Card className="space-y-3">
      <div>
        <h2 className="text-base font-medium">Connect your accounts</h2>
        <p className="text-xs text-muted-foreground mt-1">
          This agent reaches services on your behalf. Paste a token for each.
        </p>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <ul className="space-y-2">
        {required.map((req) => {
          const connectedSecret = byName.get(req.name);
          const isEditing = editing === req.name;
          return (
            <li key={req.name} className="border-t border-border pt-2 first:border-0 first:pt-0">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="font-mono text-sm">{req.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {connectedSecret
                      ? `connected · updated ${new Date(connectedSecret.updated_at).toLocaleString()}`
                      : "not connected"}
                  </div>
                </div>
                <div className="flex gap-2">
                  {connectedSecret && !isEditing && (
                    <>
                      <Badge tone="green">connected</Badge>
                      <Button
                        variant="secondary"
                        onClick={() => {
                          setEditing(req.name);
                          setDraft("");
                        }}
                        disabled={busy}
                      >
                        Replace
                      </Button>
                      <Button
                        variant="danger"
                        onClick={() => disconnect(connectedSecret.id)}
                        disabled={busy}
                      >
                        Disconnect
                      </Button>
                    </>
                  )}
                  {!connectedSecret && !isEditing && (
                    <Button
                      onClick={() => {
                        setEditing(req.name);
                        setDraft("");
                      }}
                      disabled={busy}
                    >
                      Connect
                    </Button>
                  )}
                </div>
              </div>
              {isEditing && (
                <div className="mt-2 flex gap-2 items-center">
                  <Input
                    type="password"
                    placeholder="paste your token"
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    className="flex-1"
                  />
                  <Button onClick={() => connect(req.name)} disabled={!draft || busy}>
                    Save
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => {
                      setEditing(null);
                      setDraft("");
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
