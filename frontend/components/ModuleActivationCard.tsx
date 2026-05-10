"use client";

import { Badge, Button, Card } from "@/components/ui";
import type { ModuleSpec } from "@/lib/types";

export function ModuleActivationCard({
  modules,
  enabledModules,
  editable = false,
  onToggle,
}: {
  modules: ModuleSpec[];
  enabledModules: string[];
  editable?: boolean;
  onToggle?: (moduleId: string) => void;
}) {
  const enabled = new Set(enabledModules);

  return (
    <Card className="space-y-3">
      <div>
        <h2 className="text-base font-medium">Modules</h2>
        <p className="text-xs text-muted-foreground mt-1">
          Required modules stay highlighted. Optional modules can be toggled when installation editing is enabled.
        </p>
      </div>
      {modules.length === 0 ? (
        <p className="text-sm text-muted-foreground">No modules declared.</p>
      ) : (
        <ul className="space-y-2">
          {modules.map((module) => {
            const isEnabled = enabled.has(module.id);
            return (
              <li
                key={module.id}
                className="flex items-center justify-between gap-3 border-t border-border pt-2 first:border-0 first:pt-0"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{module.title ?? module.id}</span>
                    <Badge tone={isEnabled ? "green" : "gray"}>
                      {isEnabled ? "enabled" : "disabled"}
                    </Badge>
                    {module.required && <Badge tone="amber">required</Badge>}
                  </div>
                  <p className="text-xs font-mono text-muted-foreground">{module.id}</p>
                </div>
                {editable && onToggle ? (
                  <Button
                    variant={isEnabled ? "secondary" : "primary"}
                    onClick={() => onToggle(module.id)}
                  >
                    {isEnabled ? "Disable" : "Enable"}
                  </Button>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
