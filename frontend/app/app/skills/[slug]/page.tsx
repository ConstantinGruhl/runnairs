"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { SkillTreeBrowser } from "@/components/SkillTreeBrowser";
import { Badge, Card } from "@/components/ui";
import { ApiError, apiFetch } from "@/lib/api";
import type { SkillSourceDetail } from "@/lib/types";

export default function SkillDetailPage() {
  const params = useParams<{ slug: string }>();
  const [skill, setSkill] = useState<SkillSourceDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<SkillSourceDetail>(`/app/skills/${params.slug}`)
      .then(setSkill)
      .catch((e) => setError(e instanceof ApiError ? String(e.detail) : String(e)));
  }, [params.slug]);

  if (error) {
    return <p className="text-sm text-red-600">{error}</p>;
  }
  if (skill === null) {
    return <p className="text-sm text-muted-foreground">Loading...</p>;
  }

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <Link href="/app/skills" className="text-xs text-muted-foreground hover:underline">
          Back to skills
        </Link>
        <div className="mt-2 flex items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">{skill.display_name}</h1>
            <p className="text-xs font-mono text-muted-foreground">{skill.slug}</p>
          </div>
          <Badge tone={skill.status === "ready" ? "green" : "amber"}>{skill.status}</Badge>
        </div>
      </div>

      <Card className="space-y-3">
        <div>
          <h2 className="text-base font-medium">Source</h2>
          <p className="text-xs text-muted-foreground mt-1">
            Git-backed snapshot currently available to this workspace.
          </p>
        </div>
        <dl className="space-y-2 text-sm">
          <div>
            <dt className="text-xs text-muted-foreground">Repo</dt>
            <dd className="break-all">{skill.repo_url}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Ref</dt>
            <dd className="font-mono">{skill.git_ref}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Resolved commit</dt>
            <dd className="font-mono break-all">{skill.resolved_commit_sha ?? "n/a"}</dd>
          </div>
        </dl>
      </Card>

      <Card className="space-y-3">
        <div>
          <h2 className="text-base font-medium">AI instructions</h2>
          <p className="text-xs text-muted-foreground mt-1">
            Recommended prompt or implementation guidance resolved from the package.
          </p>
        </div>
        <pre className="overflow-x-auto whitespace-pre-wrap rounded-md bg-muted p-3 text-sm">
          {skill.instructions_markdown ?? "No instructions resolved."}
        </pre>
      </Card>

      <SkillTreeBrowser entries={skill.tree} />
    </div>
  );
}
