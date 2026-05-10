"use client";

import { useState } from "react";

import { Badge, Button, Card, Input, Label } from "@/components/ui";
import { ApiError, apiFetch } from "@/lib/api";

export function AutomationScaffoldForm() {
  const [slug, setSlug] = useState("daily-digest");
  const [displayName, setDisplayName] = useState("Daily Digest");
  const [modulesRaw, setModulesRaw] = useState("summary_generation,email_delivery");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const modules = modulesRaw
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
    try {
      const response = await apiFetch<{ filename: string; archive_base64: string }>(
        "/dev/automation-scaffold",
        {
          method: "POST",
          body: JSON.stringify({
            slug,
            display_name: displayName,
            modules: modules.length > 0 ? modules : ["default"],
          }),
        },
      );
      const bytes = Uint8Array.from(atob(response.archive_base64), (char) => char.charCodeAt(0));
      const url = URL.createObjectURL(new Blob([bytes], { type: "application/zip" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = response.filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof ApiError ? String(e.detail) : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="space-y-4">
      <div className="flex items-center gap-2">
        <h2 className="text-base font-medium">Automation scaffold</h2>
        <Badge tone="blue">native</Badge>
      </div>
      <p className="text-sm text-muted-foreground">
        Generate a starter archive with `automation.yaml`, module metadata, a smoke test, and authoring instructions.
      </p>
      <form onSubmit={onSubmit} className="space-y-3">
        <div className="space-y-1.5">
          <Label htmlFor="auto-slug">Slug</Label>
          <Input id="auto-slug" value={slug} onChange={(e) => setSlug(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="auto-name">Display name</Label>
          <Input id="auto-name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="auto-modules">Modules</Label>
          <Input
            id="auto-modules"
            value={modulesRaw}
            onChange={(e) => setModulesRaw(e.target.value)}
            placeholder="summary_generation,email_delivery"
          />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <Button type="submit" disabled={busy || !slug || !displayName}>
          {busy ? "Preparing..." : "Download scaffold"}
        </Button>
      </form>
    </Card>
  );
}
