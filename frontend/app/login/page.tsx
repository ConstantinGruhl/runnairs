"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Button, Input, Label } from "@/components/ui";
import { ApiError, apiFetch } from "@/lib/api";
import { fetchBootstrapState } from "@/lib/bootstrap";
import { getUser, landingForRole, setSession } from "@/lib/auth";
import type { TokenResponse } from "@/lib/types";

export default function LoginPage() {
  const router = useRouter();
  const [checkingBootstrap, setCheckingBootstrap] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
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

      const user = getUser();
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

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await apiFetch<TokenResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setSession(res.access_token, res.user);
      router.replace(landingForRole(res.user.role));
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.status === 423) {
          router.replace("/setup");
          return;
        }
        setError(typeof e.detail === "string" ? e.detail : "login failed");
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
        Loading…
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="space-y-1 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">Agent Platform</h1>
          <p className="text-sm text-muted-foreground">
            Sign in to your workspace
          </p>
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
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          {error && (
            <p className="text-sm text-red-600">{error}</p>
          )}
          <Button type="submit" disabled={submitting} className="w-full">
            {submitting ? "Signing in…" : "Sign in"}
          </Button>
          <p className="text-center text-xs text-muted-foreground">
            Demo: admin@demo.local / demo-admin · dev@demo.local / demo-dev · user@demo.local / demo-user
          </p>
        </form>
      </div>
    </div>
  );
}
