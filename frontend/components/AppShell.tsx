"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui";
import { logout } from "@/components/RoleGuard";
import type { UserPublic } from "@/lib/types";

export function AppShell({
  user,
  section,
  navItems,
  children,
}: {
  user: UserPublic;
  section: string;
  navItems: { label: string; href: string }[];
  children: React.ReactNode;
}) {
  const router = useRouter();
  return (
    <div className="min-h-screen flex">
      <aside className="w-56 border-r border-border p-4 flex flex-col gap-4">
        <div>
          <p className="text-xs uppercase text-muted-foreground tracking-wider">
            Agent Platform
          </p>
          <p className="text-sm font-medium mt-1">{section}</p>
        </div>
        <nav className="flex flex-col gap-1">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="rounded-md px-2 py-1.5 text-sm hover:bg-muted"
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="mt-auto space-y-2 text-xs text-muted-foreground">
          <div>
            <div className="font-medium text-foreground">{user.email}</div>
            <div>{user.role}</div>
          </div>
          <Button
            variant="secondary"
            onClick={() => logout(router)}
            className="w-full"
          >
            Sign out
          </Button>
        </div>
      </aside>
      <main className="flex-1 p-6">{children}</main>
    </div>
  );
}
