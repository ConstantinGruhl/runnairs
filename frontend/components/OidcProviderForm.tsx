"use client";

import { useEffect, useState } from "react";

import { Badge, Button, Card, Input, Label } from "@/components/ui";
import { ApiError, apiFetch } from "@/lib/api";
import type {
  BootstrapState,
  OidcDiscoveryProbeResponse,
  OidcProviderPublic,
} from "@/lib/types";

type AuthMode = "built_in" | "hybrid" | "oidc";

interface OidcProviderFormState {
  name: string;
  issuer: string;
  discovery_url: string;
  client_id: string;
  client_secret: string;
  scopes: string;
  email_claim: string;
  role_claim: string;
  default_role: string;
  allow_jit_provisioning: boolean;
  manage_roles: boolean;
  is_enabled: boolean;
}

const EMPTY_FORM: OidcProviderFormState = {
  name: "",
  issuer: "",
  discovery_url: "",
  client_id: "",
  client_secret: "",
  scopes: "openid email profile",
  email_claim: "email",
  role_claim: "",
  default_role: "user",
  allow_jit_provisioning: true,
  manage_roles: false,
  is_enabled: false,
};

function detailFromError(error: unknown): string {
  if (error instanceof ApiError) {
    return typeof error.detail === "string" ? error.detail : "request failed";
  }
  return "network error";
}

function toForm(provider: OidcProviderPublic): OidcProviderFormState {
  return {
    name: provider.name,
    issuer: provider.issuer,
    discovery_url: provider.discovery_url,
    client_id: provider.client_id,
    client_secret: "",
    scopes: provider.scopes,
    email_claim: provider.email_claim,
    role_claim: provider.role_claim ?? "",
    default_role: provider.default_role,
    allow_jit_provisioning: provider.allow_jit_provisioning,
    manage_roles: provider.manage_roles,
    is_enabled: provider.is_enabled,
  };
}

function buildClaimMap(text: string, setError: (value: string | null) => void): Record<string, string> | null {
  const trimmed = text.trim();
  if (!trimmed) {
    return {};
  }
  try {
    const parsed = JSON.parse(trimmed);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      setError("claim_role_map must be a JSON object");
      return null;
    }
    const mapping: Record<string, string> = {};
    for (const [key, value] of Object.entries(parsed)) {
      if (typeof value !== "string") {
        setError(`claim_role_map value for ${key} must be a string`);
        return null;
      }
      mapping[key] = value;
    }
    return mapping;
  } catch (parseError) {
    setError(`claim_role_map is not valid JSON: ${(parseError as Error).message}`);
    return null;
  }
}

export function OidcProviderForm() {
  const [provider, setProvider] = useState<OidcProviderPublic | null>(null);
  const [bootstrapState, setBootstrapState] = useState<BootstrapState | null>(null);
  const [form, setForm] = useState<OidcProviderFormState>(EMPTY_FORM);
  const [claimMapText, setClaimMapText] = useState("{}");
  const [rotateSecret, setRotateSecret] = useState(false);
  const [probeResult, setProbeResult] = useState<OidcDiscoveryProbeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [probing, setProbing] = useState(false);

  useEffect(() => {
    void refresh();
  }, []);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [providerResp, stateResp] = await Promise.all([
        apiFetch<OidcProviderPublic | null>("/admin/oidc/provider"),
        apiFetch<BootstrapState>("/bootstrap/state"),
      ]);
      setProvider(providerResp);
      setBootstrapState(stateResp);
      if (providerResp) {
        setForm(toForm(providerResp));
        setClaimMapText(JSON.stringify(providerResp.claim_role_map ?? {}, null, 2));
      } else {
        setForm(EMPTY_FORM);
        setClaimMapText("{}");
      }
    } catch (loadError) {
      setError(detailFromError(loadError));
    } finally {
      setLoading(false);
    }
  }

  async function handleProbe() {
    setError(null);
    setSuccess(null);
    setProbing(true);
    try {
      const response = await apiFetch<OidcDiscoveryProbeResponse>("/admin/oidc/test-discovery", {
        method: "POST",
        body: JSON.stringify({ discovery_url: form.discovery_url }),
      });
      setProbeResult(response);
      setSuccess("Discovery document looks good.");
    } catch (probeError) {
      setProbeResult(null);
      setError(detailFromError(probeError));
    } finally {
      setProbing(false);
    }
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSuccess(null);
    setSubmitting(true);
    try {
      const claimRoleMap = buildClaimMap(claimMapText, setError);
      if (claimRoleMap === null) {
        setSubmitting(false);
        return;
      }
      const payload = {
        name: form.name,
        issuer: form.issuer,
        discovery_url: form.discovery_url,
        client_id: form.client_id,
        client_secret: form.client_secret || null,
        scopes: form.scopes,
        email_claim: form.email_claim,
        role_claim: form.role_claim ? form.role_claim : null,
        claim_role_map: claimRoleMap,
        default_role: form.default_role,
        allow_jit_provisioning: form.allow_jit_provisioning,
        manage_roles: form.manage_roles,
        is_enabled: form.is_enabled,
        rotate_secret: rotateSecret,
      };
      const updated = await apiFetch<OidcProviderPublic>("/admin/oidc/provider", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      setProvider(updated);
      setForm({ ...toForm(updated), client_secret: "" });
      setRotateSecret(false);
      setSuccess("Provider configuration saved.");
      await refresh();
    } catch (submitError) {
      setError(detailFromError(submitError));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete() {
    if (!provider) return;
    if (!window.confirm("Remove the configured OIDC provider? Active OIDC users will lose SSO access.")) {
      return;
    }
    setError(null);
    setSuccess(null);
    try {
      await apiFetch<void>("/admin/oidc/provider", { method: "DELETE" });
      setSuccess("Provider removed. If the instance was in OIDC mode, it has been moved back to built-in.");
      await refresh();
    } catch (deleteError) {
      setError(detailFromError(deleteError));
    }
  }

  async function handleAuthModeChange(nextMode: AuthMode) {
    if (!bootstrapState || bootstrapState.auth_mode === nextMode) return;
    if (nextMode === "oidc") {
      const confirmed = window.confirm(
        "Switching to OIDC-only mode disables built-in login for everyone except the bootstrap admin. Continue?"
      );
      if (!confirmed) return;
    }
    setError(null);
    setSuccess(null);
    try {
      const updated = await apiFetch<BootstrapState>("/bootstrap/configure", {
        method: "PUT",
        body: JSON.stringify({ auth_mode: nextMode }),
      });
      setBootstrapState(updated);
      setSuccess(`Authentication mode set to ${nextMode}.`);
    } catch (modeError) {
      setError(detailFromError(modeError));
    }
  }

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading...</p>;
  }

  return (
    <div className="space-y-6">
      <Card className="space-y-4 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Authentication mode</h2>
            <p className="text-sm text-muted-foreground">
              Choose how users sign in. Hybrid keeps both paths available; OIDC-only makes single sign-on
              authoritative and leaves built-in login active only for the bootstrap admin as a break-glass account.
            </p>
          </div>
          {bootstrapState && <Badge>{bootstrapState.auth_mode ?? "unconfigured"}</Badge>}
        </div>
        <div className="flex flex-wrap gap-2">
          {(["built_in", "hybrid", "oidc"] as AuthMode[]).map((mode) => (
            <Button
              key={mode}
              type="button"
              variant={bootstrapState?.auth_mode === mode ? "primary" : "secondary"}
              onClick={() => void handleAuthModeChange(mode)}
            >
              {mode}
            </Button>
          ))}
        </div>
        {bootstrapState && !bootstrapState.oidc_provider_state.is_enabled && (
          <p className="text-xs text-muted-foreground">
            Hybrid and OIDC modes require an enabled OIDC provider below.
          </p>
        )}
      </Card>

      <Card className="space-y-4 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">OIDC provider</h2>
            <p className="text-sm text-muted-foreground">
              Configure the OpenID Connect provider that issues SSO sessions. Use the discovery probe below
              before saving to confirm the issuer is reachable.
            </p>
          </div>
          {provider && <Badge>{provider.is_enabled ? "enabled" : "disabled"}</Badge>}
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="oidc_name">Display name</Label>
              <Input
                id="oidc_name"
                required
                value={form.name}
                onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="oidc_issuer">Issuer</Label>
              <Input
                id="oidc_issuer"
                required
                value={form.issuer}
                onChange={(event) => setForm((prev) => ({ ...prev, issuer: event.target.value }))}
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="oidc_discovery">Discovery URL</Label>
              <div className="flex gap-2">
                <Input
                  id="oidc_discovery"
                  required
                  value={form.discovery_url}
                  onChange={(event) => setForm((prev) => ({ ...prev, discovery_url: event.target.value }))}
                />
                <Button
                  type="button"
                  variant="secondary"
                  disabled={probing || !form.discovery_url}
                  onClick={() => void handleProbe()}
                >
                  {probing ? "Probing..." : "Test discovery"}
                </Button>
              </div>
              {probeResult && (
                <p className="text-xs text-muted-foreground">
                  Issuer {probeResult.issuer} reachable; authorize endpoint {probeResult.authorization_endpoint}.
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="oidc_client_id">Client ID</Label>
              <Input
                id="oidc_client_id"
                required
                value={form.client_id}
                onChange={(event) => setForm((prev) => ({ ...prev, client_id: event.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="oidc_client_secret">Client secret {provider ? "(rotate)" : ""}</Label>
              <Input
                id="oidc_client_secret"
                type="password"
                value={form.client_secret}
                onChange={(event) => setForm((prev) => ({ ...prev, client_secret: event.target.value }))}
                placeholder={provider ? "Leave blank to keep current secret" : "Required"}
              />
              {provider && (
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={rotateSecret}
                    onChange={(event) => setRotateSecret(event.target.checked)}
                  />
                  Replace the stored client secret with the value above
                </label>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="oidc_scopes">Scopes</Label>
              <Input
                id="oidc_scopes"
                value={form.scopes}
                onChange={(event) => setForm((prev) => ({ ...prev, scopes: event.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="oidc_email_claim">Email claim</Label>
              <Input
                id="oidc_email_claim"
                value={form.email_claim}
                onChange={(event) => setForm((prev) => ({ ...prev, email_claim: event.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="oidc_role_claim">Role claim (optional)</Label>
              <Input
                id="oidc_role_claim"
                value={form.role_claim}
                onChange={(event) => setForm((prev) => ({ ...prev, role_claim: event.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="oidc_default_role">Default role</Label>
              <select
                id="oidc_default_role"
                className="h-10 w-full rounded border bg-background px-3"
                value={form.default_role}
                onChange={(event) => setForm((prev) => ({ ...prev, default_role: event.target.value }))}
              >
                <option value="user">user</option>
                <option value="developer">developer</option>
                <option value="admin">admin</option>
              </select>
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="oidc_claim_role_map">Claim-to-role map (JSON object)</Label>
              <textarea
                id="oidc_claim_role_map"
                rows={4}
                className="w-full rounded border bg-background p-2 font-mono text-xs"
                value={claimMapText}
                onChange={(event) => setClaimMapText(event.target.value)}
              />
            </div>
          </div>
          <div className="flex flex-wrap gap-4 text-sm">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={form.allow_jit_provisioning}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, allow_jit_provisioning: event.target.checked }))
                }
              />
              Allow JIT provisioning
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={form.manage_roles}
                onChange={(event) => setForm((prev) => ({ ...prev, manage_roles: event.target.checked }))}
              />
              Provider may update existing user roles
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={form.is_enabled}
                onChange={(event) => setForm((prev) => ({ ...prev, is_enabled: event.target.checked }))}
              />
              Enabled
            </label>
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}
          {success && <p className="text-sm text-green-700">{success}</p>}

          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={submitting}>
              {submitting ? "Saving..." : provider ? "Save changes" : "Create provider"}
            </Button>
            {provider && (
              <Button type="button" variant="secondary" onClick={() => void handleDelete()}>
                Remove provider
              </Button>
            )}
          </div>
        </form>
      </Card>
    </div>
  );
}
