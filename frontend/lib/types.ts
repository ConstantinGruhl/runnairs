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
