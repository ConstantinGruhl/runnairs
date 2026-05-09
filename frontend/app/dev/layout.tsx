"use client";

import { AppShell } from "@/components/AppShell";
import { RoleGuard } from "@/components/RoleGuard";

const NAV = [
  { label: "Agents", href: "/dev" },
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
