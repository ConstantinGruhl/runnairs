export type UserRole = "admin" | "developer" | "user";
export type UserStatus = "active" | "disabled";

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

export interface BootstrapGuidanceItem {
  key: string;
  category: string;
  title: string;
  body: string;
  action: string;
}

export interface BootstrapOidcProviderState {
  exists: boolean;
  is_enabled: boolean;
  name: string | null;
}

export interface BootstrapState {
  bootstrap_required: boolean;
  completed: boolean;
  completed_at: string | null;
  admin_created: boolean;
  instance_admin_user_id: string | null;
  instance_admin_email: string | null;
  tenant_id: string | null;
  tenant_name: string | null;
  notification_from_email: string | null;
  auth_mode: string | null;
  supported_auth_modes: string[];
  built_in_login_enabled: boolean;
  oidc_provider_state: BootstrapOidcProviderState;
  ready_for_completion: boolean;
  blocking_reasons: string[];
  operator_guidance: BootstrapGuidanceItem[];
  checks: {
    jwt_secret_valid: boolean;
    platform_secrets_key_configured: boolean;
    database_ok: boolean;
  };
}

export interface OidcProviderPublic {
  id: string;
  name: string;
  issuer: string;
  discovery_url: string;
  client_id: string;
  has_client_secret: boolean;
  scopes: string;
  email_claim: string;
  role_claim: string | null;
  claim_role_map: Record<string, string>;
  default_role: string;
  allow_jit_provisioning: boolean;
  manage_roles: boolean;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface OidcDiscoveryProbeResponse {
  issuer: string;
  authorization_endpoint: string;
  token_endpoint: string;
  jwks_uri: string;
  userinfo_endpoint: string | null;
  end_session_endpoint: string | null;
  scopes_supported: string[];
  response_types_supported: string[];
}

export interface OidcStatusResponse {
  enabled: boolean;
  provider_name: string | null;
  login_url: string | null;
  auth_mode: string | null;
  built_in_login_enabled: boolean;
}

export interface SkillTreeEntryPublic {
  path: string;
  kind: string;
  size_bytes: number | null;
}

export interface SkillSourceSummary {
  slug: string;
  display_name: string;
  repo_url: string;
  git_ref: string;
  resolved_commit_sha: string | null;
  status: string;
  descriptor_format: string | null;
  last_synced_at: string | null;
  last_error: string | null;
}

export interface SkillSourceDetail extends SkillSourceSummary {
  instructions_markdown: string | null;
  manifest: Record<string, unknown>;
  tree: SkillTreeEntryPublic[];
}

export interface BootstrapInitializeResponse extends TokenResponse {
  bootstrap_recovery_code: string | null;
  state: BootstrapState;
}

export interface AdminUserSummary {
  id: string;
  email: string;
  role: UserRole;
  status: UserStatus;
  must_reset_password: boolean;
  password_changed_at: string;
  created_at: string;
}

export interface OneTimeCodeResponse {
  code: string;
  expires_at: string | null;
  kind: string;
}

export interface WorkspaceSecret {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface ModuleSpec {
  id: string;
  title?: string;
  required?: boolean;
  enabled_by_default?: boolean;
  depends_on_provider_plugins?: string[];
}

export interface InstallationSummary {
  status: "draft" | "ready" | "active" | "blocked";
  ready: boolean;
  enabled_modules: string[];
  missing_workspace_connections: string[];
  missing_user_connections: string[];
  disabled_required_modules: string[];
  config: Record<string, unknown>;
}

export interface ConnectionRecord {
  id: string;
  key: string;
  provider_key: string;
  scope: string;
  status: string;
  display_name: string;
  scopes?: string[];
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
  modules: ModuleSpec[];
  installation: InstallationSummary;
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

export interface AgentInstallationDetail extends InstallationSummary {
  agent_id: string;
  version_id: string;
  modules: ModuleSpec[];
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

export interface RunFeedback {
  id: string;
  run_id: string;
  user_id: string;
  rating: "up" | "down";
  comment: string | null;
  created_at: string;
}

export interface AgentFeedbackEntry {
  feedback_id: string;
  run_id: string;
  rating: "up" | "down";
  comment: string | null;
  created_at: string;
  user_id: string;
}

export interface AgentFeedbackSummary {
  agent_slug: string;
  up_count: number;
  down_count: number;
  total_runs_with_feedback: number;
  items: AgentFeedbackEntry[];
}

export interface Schedule {
  id: string;
  agent_id: string;
  cron: string;
  timezone: string;
  enabled: boolean;
  inputs_json: Record<string, unknown> | null;
  last_run_at: string | null;
  next_run_at: string | null;
  created_at: string;
}
