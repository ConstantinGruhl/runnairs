"use client";

import { useEffect, useState } from "react";

import { Button, Card, Input, Label } from "@/components/ui";
import { ApiError, apiFetch } from "@/lib/api";
import type { WorkspaceSecret } from "@/lib/types";

export default function SecretsPage() {
  const [secrets, setSecrets] = useState<WorkspaceSecret[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [value, setValue] = useState("");
  const [creating, setCreating] = useState(false);

  const [rotateId, setRotateId] = useState<string | null>(null);
  const [rotateValue, setRotateValue] = useState("");

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const rows = await apiFetch<WorkspaceSecret[]>("/admin/secrets");
      setSecrets(rows);
    } catch (e) {
      setError(formatError(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError(null);
    try {
      await apiFetch<WorkspaceSecret>("/admin/secrets", {
        method: "POST",
        body: JSON.stringify({ name, value }),
      });
      setName("");
      setValue("");
      await refresh();
    } catch (e) {
      setError(formatError(e));
    } finally {
      setCreating(false);
    }
  }

  async function handleRotate(id: string) {
    setError(null);
    try {
      await apiFetch<WorkspaceSecret>(`/admin/secrets/${id}`, {
        method: "PUT",
        body: JSON.stringify({ value: rotateValue }),
      });
      setRotateId(null);
      setRotateValue("");
      await refresh();
    } catch (e) {
      setError(formatError(e));
    }
  }

  async function handleDelete(id: string, name: string) {
    if (!confirm(`Delete secret "${name}"? Agents that depend on it will fail.`)) return;
    setError(null);
    try {
      await apiFetch<void>(`/admin/secrets/${id}`, { method: "DELETE" });
      await refresh();
    } catch (e) {
      setError(formatError(e));
    }
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Workspace secrets</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Encrypted at rest. Agents resolve these by name through the tool gateway —
          they never receive the raw value.
        </p>
      </div>

      {error && (
        <Card className="border-red-300 text-sm text-red-700">{error}</Card>
      )}

      <Card>
        <h2 className="text-base font-medium mb-3">Add a secret</h2>
        <form onSubmit={handleCreate} className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="secret-name">Name</Label>
            <Input
              id="secret-name"
              required
              pattern="[A-Za-z0-9_]+"
              value={name}
              onChange={(e) => setName(e.target.value.toUpperCase())}
              placeholder="OPENAI_API_KEY"
            />
            <p className="text-xs text-muted-foreground">
              Uppercase letters, digits, and underscores. This is the name agents
              pass to <code>secrets.get(...)</code>.
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="secret-value">Value</Label>
            <Input
              id="secret-value"
              required
              type="password"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="sk-..."
            />
          </div>
          <Button type="submit" disabled={creating}>
            {creating ? "Saving…" : "Save"}
          </Button>
        </form>
      </Card>

      <Card>
        <h2 className="text-base font-medium mb-3">
          Existing secrets ({secrets.length})
        </h2>
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : secrets.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No workspace secrets yet.
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {secrets.map((s) => (
              <li key={s.id} className="py-3 flex items-start justify-between gap-3">
                <div className="space-y-0.5">
                  <div className="font-mono text-sm">{s.name}</div>
                  <div className="text-xs text-muted-foreground">
                    Updated {new Date(s.updated_at).toLocaleString()}
                  </div>
                  {rotateId === s.id && (
                    <div className="mt-2 flex gap-2 items-center">
                      <Input
                        type="password"
                        placeholder="new value"
                        value={rotateValue}
                        onChange={(e) => setRotateValue(e.target.value)}
                        className="w-64"
                      />
                      <Button
                        variant="primary"
                        onClick={() => handleRotate(s.id)}
                        disabled={!rotateValue}
                      >
                        Save
                      </Button>
                      <Button
                        variant="ghost"
                        onClick={() => {
                          setRotateId(null);
                          setRotateValue("");
                        }}
                      >
                        Cancel
                      </Button>
                    </div>
                  )}
                </div>
                <div className="flex gap-2">
                  {rotateId !== s.id && (
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setRotateId(s.id);
                        setRotateValue("");
                      }}
                    >
                      Rotate
                    </Button>
                  )}
                  <Button
                    variant="danger"
                    onClick={() => handleDelete(s.id, s.name)}
                  >
                    Delete
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function formatError(e: unknown): string {
  if (e instanceof ApiError) {
    return typeof e.detail === "string" ? e.detail : `HTTP ${e.status}`;
  }
  return e instanceof Error ? e.message : "unknown error";
}
