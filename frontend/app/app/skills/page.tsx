"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge, Card } from "@/components/ui";
import { ApiError, apiFetch } from "@/lib/api";
import type { SkillSourceSummary } from "@/lib/types";

export default function SkillsPage() {
  const [skills, setSkills] = useState<SkillSourceSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<SkillSourceSummary[]>("/app/skills")
      .then(setSkills)
      .catch((e) => setError(e instanceof ApiError ? String(e.detail) : String(e)));
  }, []);

  if (error) {
    return <p className="text-sm text-red-600">{error}</p>;
  }
  if (skills === null) {
    return <p className="text-sm text-muted-foreground">Loading...</p>;
  }
  if (skills.length === 0) {
    return (
      <div className="space-y-3">
        <h1 className="text-2xl font-semibold">Skills</h1>
        <p className="text-sm text-muted-foreground">
          No ready Git-backed skills are registered for this workspace yet.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Skills</h1>
        <p className="text-sm text-muted-foreground">
          Browse synced Git-backed skills and inspect the instructions each one ships with.
        </p>
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {skills.map((skill) => (
          <Link key={skill.slug} href={`/app/skills/${skill.slug}`} className="block">
            <Card className="h-full space-y-3 transition hover:border-primary/40">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="font-medium">{skill.display_name}</h2>
                  <p className="text-xs font-mono text-muted-foreground">{skill.slug}</p>
                </div>
                <Badge tone={skill.status === "ready" ? "green" : "amber"}>{skill.status}</Badge>
              </div>
              <p className="text-xs text-muted-foreground break-all">
                {skill.resolved_commit_sha ?? "not synced"}
              </p>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
