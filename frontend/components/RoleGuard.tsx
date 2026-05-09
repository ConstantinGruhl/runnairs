"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { clearSession, getUser, landingForRole } from "@/lib/auth";
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
    const u = getUser();
    if (!u) {
      router.replace("/login");
      return;
    }
    if (!allow.includes(u.role)) {
      router.replace(landingForRole(u.role));
      return;
    }
    setUser(u);
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
  clearSession();
  router.replace("/login");
}
