"use client";

import { useEffect, useState } from "react";

import { Button, Card } from "@/components/ui";
import { ApiError, apiFetch } from "@/lib/api";
import type { RunFeedback } from "@/lib/types";

export function FeedbackWidget({ runId }: { runId: string }) {
  const [current, setCurrent] = useState<RunFeedback | null | "loading">("loading");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<"up" | "down" | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    apiFetch<RunFeedback | null>(`/runs/${runId}/feedback`)
      .then((r) => {
        setCurrent(r);
        if (r?.comment) setComment(r.comment);
      })
      .catch((e) => setError(e instanceof ApiError ? String(e.detail) : String(e)));
  }, [runId]);

  async function send(rating: "up" | "down") {
    setSaving(rating);
    setError(null);
    try {
      const fb = await apiFetch<RunFeedback>(`/runs/${runId}/feedback`, {
        method: "POST",
        body: JSON.stringify({ rating, comment: comment || null }),
      });
      setCurrent(fb);
      setSaved(true);
      window.setTimeout(() => setSaved(false), 1500);
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        setError("Only the user who triggered the run can leave feedback.");
      } else {
        setError(e instanceof ApiError ? String(e.detail) : String(e));
      }
    } finally {
      setSaving(null);
    }
  }

  if (current === "loading") {
    return (
      <Card>
        <h2 className="text-base font-medium mb-2">Feedback</h2>
        <p className="text-sm text-muted-foreground">Loading…</p>
      </Card>
    );
  }

  const rating = current?.rating;

  return (
    <Card className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-medium">Feedback</h2>
        {saved && <span className="text-xs text-green-700">saved</span>}
      </div>

      <div className="flex gap-2">
        <Button
          variant={rating === "up" ? "primary" : "secondary"}
          onClick={() => send("up")}
          disabled={saving !== null}
        >
          {saving === "up" ? "Saving…" : "👍 Helpful"}
        </Button>
        <Button
          variant={rating === "down" ? "primary" : "secondary"}
          onClick={() => send("down")}
          disabled={saving !== null}
        >
          {saving === "down" ? "Saving…" : "👎 Not helpful"}
        </Button>
      </div>

      <textarea
        rows={3}
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder="What worked or didn't? (optional)"
        className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary"
      />
      {current && (
        <p className="text-xs text-muted-foreground">
          You rated this run {current.rating === "up" ? "👍" : "👎"} on{" "}
          {new Date(current.created_at).toLocaleString()}.
          {comment !== (current.comment ?? "") && " (unsaved comment changes — click again)"}
        </p>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}
    </Card>
  );
}
