"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { isTerminalStatus, RunStatusBadge } from "@/components/RunStatus";
import { Card } from "@/components/ui";
import { ApiError, apiFetch } from "@/lib/api";
import type { Run } from "@/lib/types";

const POLL_INTERVAL_MS = 2000;

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);
  const stoppedRef = useRef(false);

  useEffect(() => {
    stoppedRef.current = false;

    async function tick() {
      if (stoppedRef.current) return;
      try {
        const r = await apiFetch<Run>(`/runs/${params.id}`);
        setRun(r);
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

  if (error) {
    return <p className="text-sm text-red-600">{error}</p>;
  }
  if (run === null) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

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

      <Card>
        <h2 className="text-base font-medium mb-3">Inputs</h2>
        <pre className="text-xs font-mono whitespace-pre-wrap break-words">
          {JSON.stringify(run.inputs_json ?? {}, null, 2)}
        </pre>
      </Card>

      {run.status === "awaiting_approval" && (
        <Card className="border-amber-300">
          <h2 className="text-base font-medium mb-2">Approval needed</h2>
          <p className="text-sm text-muted-foreground">
            Approval prompts wire up in Phase 7.
          </p>
        </Card>
      )}

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

      <Card>
        <h2 className="text-base font-medium mb-2">Feedback</h2>
        <p className="text-sm text-muted-foreground">
          Thumbs up/down + comment land in Phase 9.
        </p>
      </Card>

      <Card className="text-xs text-muted-foreground space-y-1">
        <div>started: {run.started_at ? new Date(run.started_at).toLocaleString() : "—"}</div>
        <div>finished: {run.finished_at ? new Date(run.finished_at).toLocaleString() : "—"}</div>
        <div>run id: <span className="font-mono">{run.id}</span></div>
      </Card>
    </div>
  );
}
