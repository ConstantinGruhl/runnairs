export type UserRole = "admin" | "developer" | "user";

export interface UserPublic {
  id: string;
  email: string;
  role: UserRole;
  tenant_id: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: UserPublic;
}

export interface WorkspaceSecret {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface CatalogEntry {
  slug: string;
  name: string;
  description: string | null;
  version: string;
  version_id: string;
  tools: string[];
  approvals_required_for: string[];
  user_secrets_needed: { name: string; scope: string }[];
}

export interface InputSpec {
  type?: string;
  required?: boolean;
  description?: string;
}

export interface CatalogDetail extends CatalogEntry {
  inputs: Record<string, InputSpec>;
  limits: {
    timeout_seconds?: number;
    memory_mb?: number;
    max_tokens?: number;
    max_cost_usd?: number;
  };
}

export type RunStatus =
  | "queued"
  | "running"
  | "awaiting_approval"
  | "succeeded"
  | "failed"
  | "cancelled";

export interface Run {
  id: string;
  agent_id: string;
  agent_slug: string | null;
  agent_name: string | null;
  agent_version_id: string;
  triggering_user_id: string | null;
  trigger: string;
  status: RunStatus;
  inputs_json: Record<string, unknown> | null;
  result_json: Record<string, unknown> | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface AgentSummary {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  status: "draft" | "approved" | "archived";
  current_version_id: string | null;
  version_count: number;
  created_at: string;
}

export interface PendingAgent {
  agent_id: string;
  slug: string;
  name: string;
  status: "draft" | "approved" | "archived";
  latest_version: string;
  latest_version_id: string;
  approved: boolean;
  manifest: Record<string, unknown>;
}

export interface Approval {
  id: string;
  run_id: string;
  action: string;
  title: string | null;
  body: string | null;
  payload_json: Record<string, unknown> | null;
  status: "pending" | "approved" | "denied";
  decided_by: string | null;
  decided_at: string | null;
  created_at: string;
}
