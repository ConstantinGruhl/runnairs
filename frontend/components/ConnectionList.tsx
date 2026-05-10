import { Badge, Card } from "@/components/ui";
import type { ConnectionRecord } from "@/lib/types";

export function ConnectionList({ connections }: { connections: ConnectionRecord[] }) {
  return (
    <Card className="space-y-3">
      <div>
        <h2 className="text-base font-medium">Workspace connections</h2>
        <p className="text-xs text-muted-foreground mt-1">
          These records describe which shared providers are configured for this workspace.
        </p>
      </div>
      {connections.length === 0 ? (
        <p className="text-sm text-muted-foreground">No workspace connections yet.</p>
      ) : (
        <ul className="space-y-2">
          {connections.map((connection) => (
            <li
              key={connection.id}
              className="flex items-center justify-between gap-3 border-t border-border pt-2 first:border-0 first:pt-0"
            >
              <div>
                <div className="font-medium">{connection.display_name}</div>
                <div className="text-xs font-mono text-muted-foreground">
                  {connection.key} · {connection.provider_key}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Badge tone={connection.status === "ready" ? "green" : "amber"}>
                  {connection.status}
                </Badge>
                <Badge tone="blue">{connection.scope}</Badge>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
