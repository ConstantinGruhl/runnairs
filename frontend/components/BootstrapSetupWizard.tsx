"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError, apiFetch } from "@/lib/api";
import { getUser, landingForRole, setSession } from "@/lib/auth";
import { fetchBootstrapState } from "@/lib/bootstrap";
import type {
  BootstrapInitializeResponse,
  BootstrapState,
  TokenResponse,
  UserPublic,
} from "@/lib/types";
import { Badge, Button, Card, Input, Label } from "@/components/ui";

const CHECK_LABELS: Record<keyof BootstrapState["checks"], string> = {
  jwt_secret_valid: "Production JWT secret is valid",
  platform_secrets_key_configured: "Secrets encryption key is configured",
  database_ok: "Database connectivity is healthy",
};

function detailFromError(error: unknown): string {
  if (error instanceof ApiError) {
    return typeof error.detail === "string" ? error.detail : "request failed";
  }
  return "network error";
}

export function BootstrapSetupWizard() {
  const router = useRouter();
  const [bootstrapState, setBootstrapState] = useState<BootstrapState | null>(null);
  const [currentUser, setCurrentUser] = useState<UserPublic | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [tenantName, setTenantName] = useState("My Workspace");
  const [adminEmail, setAdminEmail] = useState("");
  const [adminPassword, setAdminPassword] = useState("");
  const [notificationFromEmail, setNotificationFromEmail] = useState("");
  const [resumeEmail, setResumeEmail] = useState("");
  const [resumePassword, setResumePassword] = useState("");

  useEffect(() => {
    setCurrentUser(getUser());
    void refreshState();
  }, []);

  async function refreshState() {
    setLoading(true);
    setError(null);
    try {
      const state = await fetchBootstrapState();
      setBootstrapState(state);
      setTenantName(state.tenant_name || "My Workspace");
      setAdminEmail(state.instance_admin_email || "");
      setNotificationFromEmail(state.notification_from_email || "");
      setResumeEmail(state.instance_admin_email || "");

      const user = getUser();
      setCurrentUser(user);
      if (state.completed) {
        router.replace(user ? landingForRole(user.role) : "/login");
        return;
      }
    } catch (nextError) {
      setError(detailFromError(nextError));
    } finally {
      setLoading(false);
    }
  }

  async function handleInitialize(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      const response = await apiFetch<BootstrapInitializeResponse>("/bootstrap/initialize", {
        method: "POST",
        body: JSON.stringify({
          tenant_name: tenantName,
          admin_email: adminEmail,
          admin_password: adminPassword,
          notification_from_email: notificationFromEmail,
        }),
      });
      setSession(response.access_token, response.user);
      setCurrentUser(response.user);
      setBootstrapState(response.state);
      setSuccess("Bootstrap admin created. Finish the checks below to unlock the platform.");
      setAdminPassword("");
    } catch (nextError) {
      setError(detailFromError(nextError));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleResumeLogin(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      const response = await apiFetch<TokenResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: resumeEmail, password: resumePassword }),
      });
      setSession(response.access_token, response.user);
      setCurrentUser(response.user);
      setResumePassword("");
      setSuccess("Signed in. You can continue setup now.");
      await refreshState();
    } catch (nextError) {
      setError(detailFromError(nextError));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSaveConfiguration() {
    const state = await apiFetch<BootstrapState>("/bootstrap/configure", {
      method: "PUT",
      body: JSON.stringify({
        tenant_name: tenantName,
        notification_from_email: notificationFromEmail,
      }),
    });
    setBootstrapState(state);
    return state;
  }

  async function handleCompleteSetup() {
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      await handleSaveConfiguration();
      const state = await apiFetch<BootstrapState>("/bootstrap/complete", {
        method: "POST",
      });
      setBootstrapState(state);
      setSuccess("Setup complete. Redirecting to the platform.");
      const user = getUser();
      router.replace(user ? landingForRole(user.role) : "/login");
    } catch (nextError) {
      setError(detailFromError(nextError));
    } finally {
      setSubmitting(false);
    }
  }

  if (loading || bootstrapState === null) {
    return (
      <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground">
        Loading…
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-muted/30 px-4 py-10">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-6">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <h1 className="text-3xl font-semibold tracking-tight">Initial Setup</h1>
            <Badge tone={bootstrapState.ready_for_completion ? "green" : "amber"}>
              {bootstrapState.ready_for_completion ? "ready to unlock" : "configure mode"}
            </Badge>
          </div>
          <p className="max-w-2xl text-sm text-muted-foreground">
            This instance stays in configure mode until the first admin, required instance
            settings, and runtime safety checks are all complete.
          </p>
        </div>

        {error && (
          <Card className="border-red-200 bg-red-50 text-sm text-red-700">
            {error}
          </Card>
        )}

        {success && (
          <Card className="border-green-200 bg-green-50 text-sm text-green-700">
            {success}
          </Card>
        )}

        <Card className="space-y-4">
          <div className="space-y-1">
            <h2 className="text-lg font-medium">System Checks</h2>
            <p className="text-sm text-muted-foreground">
              These checks must be green before the platform can unlock normal login and routes.
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            {Object.entries(bootstrapState.checks).map(([key, ok]) => (
              <div
                key={key}
                className="rounded-md border border-border bg-background p-3 text-sm"
              >
                <div className="flex items-center justify-between gap-3">
                  <span>{CHECK_LABELS[key as keyof BootstrapState["checks"]]}</span>
                  <Badge tone={ok ? "green" : "red"}>{ok ? "ok" : "blocked"}</Badge>
                </div>
              </div>
            ))}
          </div>
          {bootstrapState.blocking_reasons.length > 0 && (
            <ul className="space-y-1 text-sm text-red-600">
              {bootstrapState.blocking_reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          )}
        </Card>

        {!bootstrapState.admin_created && (
          <Card className="space-y-4">
            <div className="space-y-1">
              <h2 className="text-lg font-medium">Create The First Admin</h2>
              <p className="text-sm text-muted-foreground">
                This creates the initial workspace tenant and the admin account that will finish
                setup and unlock the platform.
              </p>
            </div>
            <form className="grid gap-4 md:grid-cols-2" onSubmit={handleInitialize}>
              <div className="space-y-2">
                <Label htmlFor="tenant_name">Workspace name</Label>
                <Input
                  id="tenant_name"
                  required
                  value={tenantName}
                  onChange={(event) => setTenantName(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="notification_from_email">Notification from email</Label>
                <Input
                  id="notification_from_email"
                  type="email"
                  required
                  value={notificationFromEmail}
                  onChange={(event) => setNotificationFromEmail(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="admin_email">Admin email</Label>
                <Input
                  id="admin_email"
                  type="email"
                  required
                  value={adminEmail}
                  onChange={(event) => setAdminEmail(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="admin_password">Admin password</Label>
                <Input
                  id="admin_password"
                  type="password"
                  required
                  value={adminPassword}
                  onChange={(event) => setAdminPassword(event.target.value)}
                />
              </div>
              <div className="md:col-span-2">
                <Button type="submit" disabled={submitting}>
                  {submitting ? "Creating admin…" : "Create admin and continue"}
                </Button>
              </div>
            </form>
          </Card>
        )}

        {bootstrapState.admin_created && !currentUser && (
          <Card className="space-y-4">
            <div className="space-y-1">
              <h2 className="text-lg font-medium">Resume Setup</h2>
              <p className="text-sm text-muted-foreground">
                The bootstrap admin already exists. Sign in as that admin to continue configure
                mode and complete setup.
              </p>
            </div>
            <form className="grid gap-4 md:grid-cols-2" onSubmit={handleResumeLogin}>
              <div className="space-y-2">
                <Label htmlFor="resume_email">Admin email</Label>
                <Input
                  id="resume_email"
                  type="email"
                  required
                  value={resumeEmail}
                  onChange={(event) => setResumeEmail(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="resume_password">Admin password</Label>
                <Input
                  id="resume_password"
                  type="password"
                  required
                  value={resumePassword}
                  onChange={(event) => setResumePassword(event.target.value)}
                />
              </div>
              <div className="md:col-span-2">
                <Button type="submit" disabled={submitting}>
                  {submitting ? "Signing in…" : "Sign in to resume"}
                </Button>
              </div>
            </form>
          </Card>
        )}

        {bootstrapState.admin_created && currentUser && (
          <Card className="space-y-4">
            <div className="space-y-1">
              <h2 className="text-lg font-medium">Finalize Instance Configuration</h2>
              <p className="text-sm text-muted-foreground">
                Update any instance metadata that should ship with the first production-ready
                configuration, then complete setup when the checks above are all green.
              </p>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="final_tenant_name">Workspace name</Label>
                <Input
                  id="final_tenant_name"
                  required
                  value={tenantName}
                  onChange={(event) => setTenantName(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="final_notification_from_email">Notification from email</Label>
                <Input
                  id="final_notification_from_email"
                  type="email"
                  required
                  value={notificationFromEmail}
                  onChange={(event) => setNotificationFromEmail(event.target.value)}
                />
              </div>
            </div>
            <div className="flex flex-wrap gap-3">
              <Button
                type="button"
                variant="secondary"
                disabled={submitting}
                onClick={async () => {
                  setSubmitting(true);
                  setError(null);
                  setSuccess(null);
                  try {
                    const state = await handleSaveConfiguration();
                    setSuccess(
                      state.ready_for_completion
                        ? "Configuration saved. You can complete setup now."
                        : "Configuration saved. Resolve the remaining blocking checks to continue.",
                    );
                  } catch (nextError) {
                    setError(detailFromError(nextError));
                  } finally {
                    setSubmitting(false);
                  }
                }}
              >
                Save configuration
              </Button>
              <Button
                type="button"
                disabled={submitting || !bootstrapState.ready_for_completion}
                onClick={() => {
                  void handleCompleteSetup();
                }}
              >
                {submitting ? "Completing setup…" : "Complete setup"}
              </Button>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
