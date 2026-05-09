"use client";

import { AppShell } from "@/components/AppShell";
import { RoleGuard } from "@/components/RoleGuard";

const NAV = [
  { label: "Catalog", href: "/app" },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <RoleGuard allow={["user", "developer", "admin"]}>
      {(user) => (
        <AppShell user={user} section="Catalog" navItems={NAV}>
          {children}
        </AppShell>
      )}
    </RoleGuard>
  );
}
