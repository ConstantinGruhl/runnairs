"use client";

import { AppShell } from "@/components/AppShell";
import { RoleGuard } from "@/components/RoleGuard";

const NAV = [
  { label: "Secrets", href: "/admin/secrets" },
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
