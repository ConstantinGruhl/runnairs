"use client";

import { useEffect, useState } from "react";

import { SkillTreeBrowser } from "@/components/SkillTreeBrowser";
import { Badge, Button, Card, Input, Label } from "@/components/ui";
import { ApiError, apiFetch } from "@/lib/api";
import type { SkillSourceDetail, SkillSourceSummary } from "@/lib/types";

export function SkillRegistryPanel() {
  const [sources, setSources] = useState<SkillSourceSummary[] | null>(null);
  const [selected, setSelected] = useState<SkillSourceDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [slug, setSlug] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [gitRef, setGitRef] = useState("HEAD");

  async function refreshList() {
    const next = await apiFetch<SkillSourceSummary[]>("/admin/skill-sources");
    setSources(next);
    if (selected) {
      const match = next.find((item) => item.slug === selected.slug);
      if (match) {
        await loadDetail(match.slug);
      }
    }
  }

  async function loadDetail(nextSlug: string) {
    const detail = await apiFetch<SkillSourceDetail>(`/admin/skill-sources/${nextSlug}`);
    setSelected(detail);
  }

  useEffect(() => {
    refreshList().catch((e) =>
      setError(e instanceof ApiError ? String(e.detail) : String(e)),
    );
  }, []);

  async function registerSource(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const detail = await apiFetch<SkillSourceDetail>(`/admin/skill-sources/${slug}`, {
        method: "PUT",
        body: JSON.stringify({
          repo_url: repoUrl,
          git_ref: gitRef,
        }),
      });
      setSelected(detail);
      await refreshList();
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function refreshSource(nextSlug: string) {
    setBusy(true);
    setError(null);
    try {
      const detail = await apiFetch<SkillSourceDetail>(
        `/admin/skill-sources/${nextSlug}/refresh`,
        { method: "POST" },
      );
      setSelected(detail);
      await refreshList();
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-6xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Git-backed skills</h1>
        <p className="text-sm text-muted-foreground">
          Register a repository, inspect the normalized checkout, and refresh it when the source changes.
        </p>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <Card>
        <form onSubmit={registerSource} className="space-y-3">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="skill-slug">Slug</Label>
              <Input id="skill-slug" value={slug} onChange={(e) => setSlug(e.target.value)} />
            </div>
            <div className="space-y-1.5 md:col-span-2">
              <Label htmlFor="skill-repo">Repository URL or local path</Label>
              <Input id="skill-repo" value={repoUrl} onChange={(e) => setRepoUrl(e.target.value)} />
            </div>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="skill-ref">Git ref</Label>
              <Input id="skill-ref" value={gitRef} onChange={(e) => setGitRef(e.target.value)} />
            </div>
          </div>
          <Button type="submit" disabled={busy || !slug || !repoUrl}>
            {busy ? "Syncing..." : "Register or update source"}
          </Button>
        </form>
      </Card>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <Card className="space-y-3">
          <div>
            <h2 className="text-base font-medium">Registered sources</h2>
            <p className="text-xs text-muted-foreground mt-1">
              Select a source to inspect the stored manifest, instructions, and file tree.
            </p>
          </div>
          {sources === null ? (
            <p className="text-sm text-muted-foreground">Loading...</p>
          ) : sources.length === 0 ? (
            <p className="text-sm text-muted-foreground">No skill sources registered yet.</p>
          ) : (
            <ul className="space-y-2">
              {sources.map((source) => (
                <li
                  key={source.slug}
                  className="border-t border-border pt-2 first:border-0 first:pt-0"
                >
                  <button
                    type="button"
                    className="w-full text-left"
                    onClick={() => loadDetail(source.slug).catch((e) =>
                      setError(e instanceof ApiError ? String(e.detail) : String(e)),
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="font-medium">{source.display_name}</div>
                        <div className="text-xs font-mono text-muted-foreground">
                          {source.slug}
                        </div>
                      </div>
                      <Badge tone={source.status === "ready" ? "green" : source.status === "error" ? "red" : "amber"}>
                        {source.status}
                      </Badge>
                    </div>
                  </button>
                  <div className="mt-2 flex items-center justify-between gap-3">
                    <div className="text-xs text-muted-foreground break-all">
                      {source.resolved_commit_sha ?? "not synced"}
                    </div>
                    <Button
                      variant="secondary"
                      disabled={busy}
                      onClick={() => refreshSource(source.slug)}
                    >
                      Refresh
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {selected ? (
          <div className="space-y-6">
            <Card className="space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-base font-medium">{selected.display_name}</h2>
                  <p className="text-xs font-mono text-muted-foreground">{selected.slug}</p>
                </div>
                <Badge tone={selected.status === "ready" ? "green" : selected.status === "error" ? "red" : "amber"}>
                  {selected.status}
                </Badge>
              </div>
              <dl className="space-y-2 text-sm">
                <div>
                  <dt className="text-xs text-muted-foreground">Repo</dt>
                  <dd className="break-all">{selected.repo_url}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Ref</dt>
                  <dd className="font-mono">{selected.git_ref}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Resolved commit</dt>
                  <dd className="font-mono break-all">{selected.resolved_commit_sha ?? "n/a"}</dd>
                </div>
              </dl>
              {selected.last_error && (
                <p className="text-sm text-red-600">{selected.last_error}</p>
              )}
            </Card>

            <Card className="space-y-3">
              <div>
                <h2 className="text-base font-medium">AI instructions</h2>
                <p className="text-xs text-muted-foreground mt-1">
                  Resolved from `AI_INSTRUCTIONS.md`, `SKILL.md`, `README.md`, or manifest fallback.
                </p>
              </div>
              <pre className="overflow-x-auto whitespace-pre-wrap rounded-md bg-muted p-3 text-sm">
                {selected.instructions_markdown ?? "No instructions resolved."}
              </pre>
            </Card>

            <SkillTreeBrowser entries={selected.tree} />
          </div>
        ) : (
          <Card>
            <p className="text-sm text-muted-foreground">
              Select a registered source to inspect it.
            </p>
          </Card>
        )}
      </div>
    </div>
  );
}
