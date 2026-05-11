"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { getUser, landingForRole, logoutSession, refreshCurrentUser } from "@/lib/auth";
import { fetchBootstrapState } from "@/lib/bootstrap";
import type { UserPublic, UserRole } from "@/lib/types";

export function RoleGuard({
  allow,
  children,
}: {
  allow: UserRole[];
  children: (user: UserPublic) => React.ReactNode;
}) {
  const router = useRouter();
  const [user, setUser] = useState<UserPublic | null | "loading">("loading");

  useEffect(() => {
    let cancelled = false;

    async function resolveAccess() {
      try {
        const bootstrapState = await fetchBootstrapState();
        if (cancelled) return;
        if (bootstrapState.bootstrap_required) {
          router.replace("/setup");
          return;
        }
      } catch {
        // Fall back to the current local session behavior if the bootstrap API is unavailable.
      }

      const u = await refreshCurrentUser().catch(() => getUser());
      if (!u) {
        router.replace("/login");
        return;
      }
      if (!allow.includes(u.role)) {
        router.replace(landingForRole(u.role));
        return;
      }
      setUser(u);
    }

    void resolveAccess();
    return () => {
      cancelled = true;
    };
  }, [router, allow]);

  if (user === "loading" || user === null) {
    return (
      <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground">
        Loading…
      </div>
    );
  }

  return (
    <>
      {children(user)}
    </>
  );
}

export function logout(router: ReturnType<typeof useRouter>): void {
  void logoutSession().finally(() => {
    router.replace("/login");
  });
}
