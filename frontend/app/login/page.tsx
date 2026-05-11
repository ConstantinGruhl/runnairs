"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { Button, Input, Label } from "@/components/ui";
import { SsoLoginButton } from "@/components/SsoLoginButton";
import { ApiError, apiFetch } from "@/lib/api";
import { fetchBootstrapState } from "@/lib/bootstrap";
import { getUser, landingForRole, refreshCurrentUser, setSession } from "@/lib/auth";
import type { TokenResponse } from "@/lib/types";

type LoginMode = "login" | "password_reset" | "recovery";

const OIDC_ERROR_COPY: Record<string, string> = {
  invalid_state: "Single sign-on flow expired or was tampered with. Please try again.",
  expired_flow: "Single sign-on flow expired. Please try again.",
  email_mismatch: "The email returned by your provider does not match the linked account.",
  provisioning_disabled: "Your account does not exist yet and just-in-time provisioning is disabled.",
  account_disabled: "Your account is disabled. Contact an administrator.",
  provider_disabled: "Single sign-on is currently disabled on this instance.",
  idp_error: "Single sign-on provider returned an error. Please try again.",
  unknown: "Single sign-on failed unexpectedly. Please try again.",
};

export default function LoginPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground">
        Loading...
      </div>
    }>
      <LoginPageInner />
    </Suspense>
  );
}

function LoginPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const oidcErrorCode = searchParams.get("oidc_error");
  const [checkingBootstrap, setCheckingBootstrap] = useState(true);
  const [mode, setMode] = useState<LoginMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [resetCode, setResetCode] = useState("");
  const [recoveryCode, setRecoveryCode] = useState("");
  const [error, setError] = useState<string | null>(
    oidcErrorCode ? OIDC_ERROR_COPY[oidcErrorCode] ?? OIDC_ERROR_COPY.unknown : null
  );
  const [success, setSuccess] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function resolveRoute() {
      try {
        const state = await fetchBootstrapState();
        if (cancelled) return;
        if (state.bootstrap_required) {
          router.replace("/setup");
          return;
        }
      } catch {
        // Keep the login form available if bootstrap state is temporarily unreachable.
      }

      const user = await refreshCurrentUser().catch(() => getUser());
      if (cancelled) return;
      if (user) {
        router.replace(landingForRole(user.role));
        return;
      }
      setCheckingBootstrap(false);
    }

    void resolveRoute();
    return () => {
      cancelled = true;
    };
  }, [router]);

  async function completeSession(response: TokenResponse) {
    setSession(response.access_token, response.user);
    router.replace(landingForRole(response.user.role));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSuccess(null);
    setSubmitting(true);

    try {
      if (mode === "login") {
        const response = await apiFetch<TokenResponse>("/auth/login", {
          method: "POST",
          body: JSON.stringify({ email, password }),
        });
        await completeSession(response);
        return;
      }

      if (mode === "password_reset") {
        const response = await apiFetch<TokenResponse>("/auth/password-reset/complete", {
          method: "POST",
          body: JSON.stringify({
            email,
            reset_code: resetCode,
            new_password: newPassword,
          }),
        });
        setSuccess("Password reset complete. Redirecting to your workspace.");
        await completeSession(response);
        return;
      }

      const response = await apiFetch<TokenResponse>("/auth/recovery/complete", {
        method: "POST",
        body: JSON.stringify({
          email,
          recovery_code: recoveryCode,
          new_password: newPassword,
        }),
      });
      setSuccess("Recovery complete. Redirecting to your workspace.");
      await completeSession(response);
    } catch (nextError) {
      if (nextError instanceof ApiError) {
        if (nextError.status === 423) {
          router.replace("/setup");
          return;
        }
        setError(typeof nextError.detail === "string" ? nextError.detail : "authentication failed");
      } else {
        setError("network error");
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (checkingBootstrap) {
    return (
      <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground">
        Loading...
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-md space-y-6">
        <div className="space-y-1 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">Agent Platform</h1>
          <p className="text-sm text-muted-foreground">
            {mode === "login"
              ? "Sign in to your workspace"
              : mode === "password_reset"
                ? "Complete a password reset with an admin-issued code"
                : "Recover the bootstrap admin with the offline recovery code"}
          </p>
        </div>

        <SsoLoginButton />

        <div className="flex flex-wrap justify-center gap-2">
          <Button type="button" variant={mode === "login" ? "primary" : "secondary"} onClick={() => setMode("login")}>
            Sign in
          </Button>
          <Button
            type="button"
            variant={mode === "password_reset" ? "primary" : "secondary"}
            onClick={() => setMode("password_reset")}
          >
            Use reset code
          </Button>
          <Button
            type="button"
            variant={mode === "recovery" ? "primary" : "secondary"}
            onClick={() => setMode("recovery")}
          >
            Use recovery code
          </Button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@company.com"
            />
          </div>

          {mode === "login" && (
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>
          )}

          {mode === "password_reset" && (
            <>
              <div className="space-y-2">
                <Label htmlFor="reset_code">Password reset code</Label>
                <Input
                  id="reset_code"
                  required
                  value={resetCode}
                  onChange={(event) => setResetCode(event.target.value)}
                  placeholder="Paste the code from your admin"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="new_password_reset">New password</Label>
                <Input
                  id="new_password_reset"
                  type="password"
                  required
                  value={newPassword}
                  onChange={(event) => setNewPassword(event.target.value)}
                  placeholder="At least 12 characters with letters and numbers"
                />
              </div>
            </>
          )}

          {mode === "recovery" && (
            <>
              <div className="space-y-2">
                <Label htmlFor="recovery_code">Recovery code</Label>
                <Input
                  id="recovery_code"
                  required
                  value={recoveryCode}
                  onChange={(event) => setRecoveryCode(event.target.value)}
                  placeholder="Paste the offline bootstrap recovery code"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="new_password_recovery">New password</Label>
                <Input
                  id="new_password_recovery"
                  type="password"
                  required
                  value={newPassword}
                  onChange={(event) => setNewPassword(event.target.value)}
                  placeholder="At least 12 characters with letters and numbers"
                />
              </div>
            </>
          )}

          {error && <p className="text-sm text-red-600">{error}</p>}
          {success && <p className="text-sm text-green-700">{success}</p>}

          <Button type="submit" disabled={submitting} className="w-full">
            {submitting
              ? mode === "login"
                ? "Signing in..."
                : mode === "password_reset"
                  ? "Resetting password..."
                  : "Completing recovery..."
              : mode === "login"
                ? "Sign in"
                : mode === "password_reset"
                  ? "Complete password reset"
                  : "Complete recovery"}
          </Button>

          {mode === "login" && (
            <p className="text-center text-xs text-muted-foreground">
              Demo: admin@demo.local / demo-admin · dev@demo.local / demo-dev · user@demo.local / demo-user
            </p>
          )}
        </form>
      </div>
    </div>
  );
}
