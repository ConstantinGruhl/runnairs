"use client";

import { Card } from "@/components/ui";
import type { SkillTreeEntryPublic } from "@/lib/types";

export function SkillTreeBrowser({
  entries,
  title = "Files",
}: {
  entries: SkillTreeEntryPublic[];
  title?: string;
}) {
  return (
    <Card className="space-y-3">
      <div>
        <h2 className="text-base font-medium">{title}</h2>
        <p className="text-xs text-muted-foreground mt-1">
          Sanitized checkout snapshot exposed for inspection.
        </p>
      </div>
      {entries.length === 0 ? (
        <p className="text-sm text-muted-foreground">No tracked files yet.</p>
      ) : (
        <ul className="space-y-2">
          {entries.map((entry) => (
            <li
              key={`${entry.kind}:${entry.path}`}
              className="flex items-center justify-between gap-3 border-t border-border pt-2 first:border-0 first:pt-0"
            >
              <div className="min-w-0">
                <div className="font-mono text-xs break-all">{entry.path}</div>
              </div>
              <div className="shrink-0 text-xs text-muted-foreground">
                {entry.kind === "directory"
                  ? "dir"
                  : `${entry.size_bytes ?? 0} bytes`}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
