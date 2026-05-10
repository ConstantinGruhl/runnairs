"use client";

import { AppShell } from "@/components/AppShell";
import { RoleGuard } from "@/components/RoleGuard";

const NAV = [
  { label: "Agents", href: "/dev" },
  { label: "New Automation", href: "/dev/automations/new" },
];

export default function DevLayout({ children }: { children: React.ReactNode }) {
  return (
    <RoleGuard allow={["developer", "admin"]}>
      {(user) => (
        <AppShell user={user} section="Developer" navItems={NAV}>
          {children}
        </AppShell>
      )}
    </RoleGuard>
  );
}
