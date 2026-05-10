import { Badge, Card } from "@/components/ui";

export function InstallationReadinessCard({
  ready,
  missingWorkspaceConnections,
  missingUserConnections,
  disabledRequiredModules = [],
}: {
  ready: boolean;
  missingWorkspaceConnections: string[];
  missingUserConnections: string[];
  disabledRequiredModules?: string[];
}) {
  return (
    <Card className="space-y-3">
      <div className="flex items-center gap-2">
        <h2 className="text-base font-medium">Installation readiness</h2>
        <Badge tone={ready ? "green" : "amber"}>{ready ? "ready" : "attention needed"}</Badge>
      </div>
      <div className="space-y-2 text-sm">
        <ReadinessRow
          label="Workspace connections"
          values={missingWorkspaceConnections}
          emptyLabel="all configured"
        />
        <ReadinessRow
          label="User connections"
          values={missingUserConnections}
          emptyLabel="all configured"
        />
        <ReadinessRow
          label="Required modules"
          values={disabledRequiredModules}
          emptyLabel="all enabled"
        />
      </div>
    </Card>
  );
}


function ReadinessRow({
  label,
  values,
  emptyLabel,
}: {
  label: string;
  values: string[];
  emptyLabel: string;
}) {
  return (
    <div className="space-y-1">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      {values.length === 0 ? (
        <p className="text-sm text-muted-foreground">{emptyLabel}</p>
      ) : (
        <div className="flex flex-wrap gap-1">
          {values.map((value) => (
            <Badge key={value} tone="amber">
              {value}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}
