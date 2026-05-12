"use client";

import { AppShell } from "@/components/AppShell";
import { RoleGuard } from "@/components/RoleGuard";

const NAV = [
  { label: "Catalog", href: "/app" },
  { label: "Skills", href: "/app/skills" },
  { label: "My runs", href: "/app/runs" },
  { label: "Docs", href: "/app/docs" },
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
