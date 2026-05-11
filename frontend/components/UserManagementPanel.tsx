"use client";

import { useEffect, useState } from "react";

import { ApiError, apiFetch } from "@/lib/api";
import type { AdminUserSummary, OneTimeCodeResponse, UserRole, UserStatus } from "@/lib/types";
import { Badge, Button, Card, Input, Label } from "@/components/ui";

type UserEditorState = {
  role: UserRole;
  status: UserStatus;
};

function detailFromError(error: unknown): string {
  if (error instanceof ApiError) {
    return typeof error.detail === "string" ? error.detail : "request failed";
  }
  return "network error";
}

export function UserManagementPanel() {
  const [users, setUsers] = useState<AdminUserSummary[]>([]);
  const [drafts, setDrafts] = useState<Record<string, UserEditorState>>({});
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("developer");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [generatedCode, setGeneratedCode] = useState<{
    email: string;
    payload: OneTimeCodeResponse;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    void refresh();
  }, []);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const nextUsers = await apiFetch<AdminUserSummary[]>("/admin/users");
      setUsers(nextUsers);
      setDrafts(
        Object.fromEntries(
          nextUsers.map((user) => [
            user.id,
            {
              role: user.role,
              status: user.status,
            },
          ]),
        ),
      );
    } catch (nextError) {
      setError(detailFromError(nextError));
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateUser(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      await apiFetch<AdminUserSummary>("/admin/users", {
        method: "POST",
        body: JSON.stringify({
          email,
          password,
          role,
        }),
      });
      setEmail("");
      setPassword("");
      setRole("developer");
      setSuccess("User created.");
      await refresh();
    } catch (nextError) {
      setError(detailFromError(nextError));
    } finally {
      setSubmitting(false);
    }
  }

  async function saveUser(userId: string) {
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      await apiFetch<AdminUserSummary>(`/admin/users/${userId}`, {
        method: "PATCH",
        body: JSON.stringify(drafts[userId]),
      });
      setSuccess("User updated.");
      await refresh();
    } catch (nextError) {
      setError(detailFromError(nextError));
    } finally {
      setSubmitting(false);
    }
  }

  async function issueCode(user: AdminUserSummary, path: "password-reset" | "recovery-code") {
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      const payload = await apiFetch<OneTimeCodeResponse>(`/admin/users/${user.id}/${path}`, {
        method: "POST",
      });
      setGeneratedCode({ email: user.email, payload });
      setSuccess(`${payload.kind === "recovery" ? "Recovery" : "Reset"} code generated.`);
    } catch (nextError) {
      setError(detailFromError(nextError));
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading users...</p>;
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold">Users</h1>
        <p className="text-sm text-muted-foreground">
          Manage built-in IAM accounts, roles, status, and one-time reset or recovery codes.
        </p>
      </div>

      {error && <Card className="border-red-200 bg-red-50 text-sm text-red-700">{error}</Card>}
      {success && <Card className="border-green-200 bg-green-50 text-sm text-green-700">{success}</Card>}

      {generatedCode && (
        <Card className="space-y-3 border-blue-200 bg-blue-50">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-medium">{generatedCode.payload.kind === "recovery" ? "Recovery code" : "Password reset code"}</h2>
              <p className="text-sm text-blue-950/80">
                Share this once with {generatedCode.email}. The server only stores the hash.
              </p>
            </div>
            <Badge tone="blue">one time</Badge>
          </div>
          <pre className="overflow-x-auto rounded-md border border-blue-200 bg-background px-3 py-2 text-sm font-mono">
            {generatedCode.payload.code}
          </pre>
          {generatedCode.payload.expires_at && (
            <p className="text-xs text-muted-foreground">
              Expires: {new Date(generatedCode.payload.expires_at).toLocaleString()}
            </p>
          )}
        </Card>
      )}

      <Card className="space-y-4">
        <div className="space-y-1">
          <h2 className="text-lg font-medium">Create User</h2>
          <p className="text-sm text-muted-foreground">
            Create a built-in IAM account with an initial password. Users can later be reset from this page.
          </p>
        </div>
        <form className="grid gap-4 md:grid-cols-3" onSubmit={handleCreateUser}>
          <div className="space-y-2">
            <Label htmlFor="new_user_email">Email</Label>
            <Input
              id="new_user_email"
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="new_user_password">Initial password</Label>
            <Input
              id="new_user_password"
              type="password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="At least 12 characters with letters and numbers"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="new_user_role">Role</Label>
            <select
              id="new_user_role"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              value={role}
              onChange={(event) => setRole(event.target.value as UserRole)}
            >
              <option value="admin">admin</option>
              <option value="developer">developer</option>
              <option value="user">user</option>
            </select>
          </div>
          <div className="md:col-span-3">
            <Button type="submit" disabled={submitting}>
              {submitting ? "Creating user..." : "Create user"}
            </Button>
          </div>
        </form>
      </Card>

      <div className="grid gap-4">
        {users.map((user) => (
          <Card key={user.id} className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="font-medium text-foreground">{user.email}</p>
                <p className="text-xs text-muted-foreground">
                  Created {new Date(user.created_at).toLocaleString()}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Badge tone={user.status === "active" ? "green" : "red"}>{user.status}</Badge>
                <Badge tone="blue">{user.role}</Badge>
                {user.must_reset_password && <Badge tone="amber">reset pending</Badge>}
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor={`role-${user.id}`}>Role</Label>
                <select
                  id={`role-${user.id}`}
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                  value={drafts[user.id]?.role ?? user.role}
                  onChange={(event) =>
                    setDrafts((current) => ({
                      ...current,
                      [user.id]: {
                        ...(current[user.id] ?? { role: user.role, status: user.status }),
                        role: event.target.value as UserRole,
                      },
                    }))
                  }
                >
                  <option value="admin">admin</option>
                  <option value="developer">developer</option>
                  <option value="user">user</option>
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor={`status-${user.id}`}>Status</Label>
                <select
                  id={`status-${user.id}`}
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                  value={drafts[user.id]?.status ?? user.status}
                  onChange={(event) =>
                    setDrafts((current) => ({
                      ...current,
                      [user.id]: {
                        ...(current[user.id] ?? { role: user.role, status: user.status }),
                        status: event.target.value as UserStatus,
                      },
                    }))
                  }
                >
                  <option value="active">active</option>
                  <option value="disabled">disabled</option>
                </select>
              </div>
            </div>

            <div className="flex flex-wrap gap-3">
              <Button type="button" variant="secondary" disabled={submitting} onClick={() => void saveUser(user.id)}>
                Save changes
              </Button>
              <Button
                type="button"
                variant="secondary"
                disabled={submitting}
                onClick={() => void issueCode(user, "password-reset")}
              >
                Generate reset code
              </Button>
              <Button
                type="button"
                variant="secondary"
                disabled={submitting}
                onClick={() => void issueCode(user, "recovery-code")}
              >
                Generate recovery code
              </Button>
            </div>

            <p className="text-xs text-muted-foreground">
              Password last changed: {new Date(user.password_changed_at).toLocaleString()}
            </p>
          </Card>
        ))}
      </div>
    </div>
  );
}
