"use client";

import { AppShell } from "@/components/AppShell";
import { RoleGuard } from "@/components/RoleGuard";

const NAV = [
  { label: "Agents", href: "/admin/agents" },
  { label: "Connections", href: "/admin/connections" },
  { label: "Secrets", href: "/admin/secrets" },
  { label: "Docs", href: "/admin/docs" },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <RoleGuard allow={["admin"]}>
      {(user) => (
        <AppShell user={user} section="Admin" navItems={NAV}>
          {children}
        </AppShell>
      )}
    </RoleGuard>
  );
}
