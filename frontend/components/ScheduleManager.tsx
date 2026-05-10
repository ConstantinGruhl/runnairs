"use client";

import { useEffect, useState } from "react";

import { Badge, Button, Card, Input, Label } from "@/components/ui";
import { ApiError, apiFetch } from "@/lib/api";
import type { Schedule } from "@/lib/types";

export function ScheduleManager({ slug }: { slug: string }) {
  const [schedules, setSchedules] = useState<Schedule[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [cron, setCron] = useState("");
  const [timezone, setTimezone] = useState("UTC");
  const [inputsRaw, setInputsRaw] = useState("");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    try {
      setSchedules(await apiFetch<Schedule[]>(`/dev/agents/${slug}/schedules`));
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : String(e));
    }
  }

  useEffect(() => {
    refresh();
  }, [slug]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    let inputs: unknown = null;
    if (inputsRaw.trim()) {
      try {
        inputs = JSON.parse(inputsRaw);
      } catch (err) {
        setError(`inputs must be JSON: ${err instanceof Error ? err.message : err}`);
        setBusy(false);
        return;
      }
    }
    try {
      await apiFetch<Schedule>(`/dev/agents/${slug}/schedules`, {
        method: "POST",
        body: JSON.stringify({ cron, timezone, inputs, enabled: true }),
      });
      setCron("");
      setInputsRaw("");
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function toggle(s: Schedule) {
    setBusy(true);
    setError(null);
    try {
      await apiFetch<Schedule>(`/dev/schedules/${s.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !s.enabled }),
      });
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove(s: Schedule) {
    if (!confirm(`Delete schedule "${s.cron}"?`)) return;
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/dev/schedules/${s.id}`, { method: "DELETE" });
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="space-y-3">
      <div>
        <h2 className="text-base font-medium">Schedules</h2>
        <p className="text-xs text-muted-foreground mt-1">
          Cron expressions in the workspace timezone. The scheduler ticks every 30s.
        </p>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {schedules === null ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : schedules.length === 0 ? (
        <p className="text-sm text-muted-foreground">No schedules yet.</p>
      ) : (
        <ul className="divide-y divide-border">
          {schedules.map((s) => (
            <li key={s.id} className="py-2.5 flex items-start justify-between gap-3">
              <div className="space-y-0.5">
                <div className="flex items-center gap-2">
                  <code className="font-mono text-sm">{s.cron}</code>
                  <Badge tone={s.enabled ? "green" : "gray"}>
                    {s.enabled ? "enabled" : "paused"}
                  </Badge>
                  <span className="text-xs text-muted-foreground">{s.timezone}</span>
                </div>
                <div className="text-xs text-muted-foreground">
                  next: {s.next_run_at ? new Date(s.next_run_at).toLocaleString() : "—"}
                  {" · "}
                  last: {s.last_run_at ? new Date(s.last_run_at).toLocaleString() : "—"}
                </div>
                {s.inputs_json && Object.keys(s.inputs_json).length > 0 && (
                  <pre className="text-xs font-mono text-muted-foreground mt-1">
                    {JSON.stringify(s.inputs_json)}
                  </pre>
                )}
              </div>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={() => toggle(s)} disabled={busy}>
                  {s.enabled ? "Pause" : "Resume"}
                </Button>
                <Button variant="danger" onClick={() => remove(s)} disabled={busy}>
                  Delete
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={create} className="space-y-3 border-t border-border pt-3">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="sched-cron">Cron</Label>
            <Input
              id="sched-cron"
              required
              placeholder="* * * * *"
              value={cron}
              onChange={(e) => setCron(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="sched-tz">Timezone</Label>
            <Input
              id="sched-tz"
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
            />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="sched-inputs">Inputs JSON (optional)</Label>
          <textarea
            id="sched-inputs"
            rows={2}
            value={inputsRaw}
            onChange={(e) => setInputsRaw(e.target.value)}
            placeholder='{"region":"EMEA","recipient_email":"a@b.com"}'
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm font-mono outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
        <Button type="submit" disabled={busy || !cron}>
          Add schedule
        </Button>
      </form>
    </Card>
  );
}
