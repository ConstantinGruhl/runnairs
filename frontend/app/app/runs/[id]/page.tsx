"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { FeedbackWidget } from "@/components/FeedbackWidget";
import { isTerminalStatus, RunStatusBadge } from "@/components/RunStatus";
import { Badge, Button, Card } from "@/components/ui";
import { ApiError, apiFetch } from "@/lib/api";
import { getUser } from "@/lib/auth";
import type { Approval, Run } from "@/lib/types";

const POLL_INTERVAL_MS = 2000;

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const [run, setRun] = useState<Run | null>(null);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [error, setError] = useState<string | null>(null);
  const stoppedRef = useRef(false);
  const isAdmin = getUser()?.role === "admin";

  useEffect(() => {
    stoppedRef.current = false;

    async function tick() {
      if (stoppedRef.current) return;
      try {
        const [r, ap] = await Promise.all([
          apiFetch<Run>(`/runs/${params.id}`),
          apiFetch<Approval[]>(`/runs/${params.id}/approvals`).catch(() => [] as Approval[]),
        ]);
        setRun(r);
        setApprovals(ap);
        if (isTerminalStatus(r.status)) {
          stoppedRef.current = true;
          return;
        }
      } catch (e) {
        setError(e instanceof ApiError ? String(e.detail) : String(e));
        stoppedRef.current = true;
        return;
      }
      window.setTimeout(tick, POLL_INTERVAL_MS);
    }

    tick();

    return () => {
      stoppedRef.current = true;
    };
  }, [params.id]);

  async function decide(approvalId: string, decision: "approved" | "denied") {
    try {
      await apiFetch(`/admin/approvals/${approvalId}/decide`, {
        method: "POST",
        body: JSON.stringify({ decision }),
      });
      // Force a fresh fetch on the next tick.
      const [r, ap] = await Promise.all([
        apiFetch<Run>(`/runs/${params.id}`),
        apiFetch<Approval[]>(`/runs/${params.id}/approvals`).catch(() => []),
      ]);
      setRun(r);
      setApprovals(ap);
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : String(e));
    }
  }

  if (error) {
    return <p className="text-sm text-red-600">{error}</p>;
  }
  if (run === null) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  const pendingApprovals = approvals.filter((a) => a.status === "pending");

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <Link
          href={run.agent_slug ? `/app/agents/${run.agent_slug}` : "/app"}
          className="text-xs text-muted-foreground hover:underline"
        >
          ← back to {run.agent_name ?? "catalog"}
        </Link>
        <div className="flex items-center gap-3 mt-2">
          <h1 className="text-2xl font-semibold">
            Run {run.id.slice(0, 8)}…
          </h1>
          <RunStatusBadge status={run.status} />
        </div>
        <p className="text-xs text-muted-foreground mt-1">
          {run.agent_name ?? run.agent_slug ?? "agent"} · {run.trigger}
        </p>
      </div>

      {pendingApprovals.length > 0 && (
        <Card className="border-amber-300 space-y-3">
          <div className="flex items-center gap-2">
            <h2 className="text-base font-medium">Approval needed</h2>
            <Badge tone="amber">paused</Badge>
          </div>
          {pendingApprovals.map((a) => (
            <div key={a.id} className="border-t border-amber-200 pt-3 first:border-0 first:pt-0 space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">{a.title ?? a.action}</span>
                <Badge>{a.action}</Badge>
              </div>
              {a.body && (
                <pre className="text-xs whitespace-pre-wrap break-words bg-muted/40 p-2 rounded">
                  {a.body}
                </pre>
              )}
              {isAdmin ? (
                <div className="flex gap-2">
                  <Button onClick={() => decide(a.id, "approved")}>Approve</Button>
                  <Button variant="danger" onClick={() => decide(a.id, "denied")}>
                    Deny
                  </Button>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Only an admin can decide this approval.
                </p>
              )}
            </div>
          ))}
        </Card>
      )}

      <Card>
        <h2 className="text-base font-medium mb-3">Inputs</h2>
        <pre className="text-xs font-mono whitespace-pre-wrap break-words">
          {JSON.stringify(run.inputs_json ?? {}, null, 2)}
        </pre>
      </Card>

      {(run.status === "queued" || run.status === "running") && (
        <Card className="border-blue-300">
          <h2 className="text-base font-medium mb-2">Live</h2>
          <p className="text-sm text-muted-foreground">
            Polling every 2s — status: <strong>{run.status}</strong>.
          </p>
          {run.started_at && (
            <p className="text-xs text-muted-foreground mt-1">
              started {new Date(run.started_at).toLocaleString()}
            </p>
          )}
        </Card>
      )}

      {run.status === "succeeded" && (
        <Card>
          <h2 className="text-base font-medium mb-3">Result</h2>
          {run.result_json ? (
            <pre className="text-xs font-mono whitespace-pre-wrap break-words">
              {JSON.stringify(run.result_json, null, 2)}
            </pre>
          ) : (
            <p className="text-sm text-muted-foreground">(empty result)</p>
          )}
        </Card>
      )}

      {run.status === "failed" && (
        <Card className="border-red-300">
          <h2 className="text-base font-medium mb-2 text-red-700">Failed</h2>
          <pre className="text-xs font-mono whitespace-pre-wrap break-words text-red-700">
            {run.error ?? "(no error message)"}
          </pre>
        </Card>
      )}

      {approvals.length > 0 && pendingApprovals.length === 0 && (
        <Card>
          <h2 className="text-base font-medium mb-3">Approvals</h2>
          <ul className="divide-y divide-border">
            {approvals.map((a) => (
              <li key={a.id} className="py-2.5 flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm">{a.title ?? a.action}</div>
                  <div className="text-xs text-muted-foreground">{a.action}</div>
                </div>
                <Badge tone={a.status === "approved" ? "green" : a.status === "denied" ? "red" : "muted"}>
                  {a.status}
                </Badge>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {isTerminalStatus(run.status) && <FeedbackWidget runId={run.id} />}

      <Card className="text-xs text-muted-foreground space-y-1">
        <div>started: {run.started_at ? new Date(run.started_at).toLocaleString() : "—"}</div>
        <div>finished: {run.finished_at ? new Date(run.finished_at).toLocaleString() : "—"}</div>
        <div>run id: <span className="font-mono">{run.id}</span></div>
      </Card>
    </div>
  );
}
