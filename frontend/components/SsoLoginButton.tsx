"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui";
import { apiFetch } from "@/lib/api";
import type { OidcStatusResponse } from "@/lib/types";

interface SsoLoginButtonProps {
  next?: string;
}

export function SsoLoginButton({ next }: SsoLoginButtonProps) {
  const [status, setStatus] = useState<OidcStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch<OidcStatusResponse>("/auth/oidc/status")
      .then((value) => {
        if (!cancelled) setStatus(value);
      })
      .catch(() => {
        if (!cancelled) setError("unable to determine OIDC status");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return <p className="text-xs text-muted-foreground">{error}</p>;
  }
  if (!status || !status.enabled || !status.login_url) {
    return null;
  }

  const href = next ? `${status.login_url}?next=${encodeURIComponent(next)}` : status.login_url;

  return (
    <div className="space-y-2">
      <a href={href} className="block">
        <Button type="button" variant="secondary" className="w-full">
          Continue with {status.provider_name ?? "single sign-on"}
        </Button>
      </a>
      {!status.built_in_login_enabled && (
        <p className="text-xs text-muted-foreground text-center">
          Built-in login is disabled while this instance is in OIDC-authoritative mode. The bootstrap admin retains a break-glass account.
        </p>
      )}
    </div>
  );
}
