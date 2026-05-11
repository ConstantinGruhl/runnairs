"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { getUser, landingForRole } from "@/lib/auth";
import { fetchBootstrapState } from "@/lib/bootstrap";

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;

    async function resolveLanding() {
      try {
        const state = await fetchBootstrapState();
        if (cancelled) return;
        if (state.bootstrap_required) {
          router.replace("/setup");
          return;
        }
      } catch {
        // Fall through to the existing local session redirect if the API is not reachable yet.
      }

      const user = getUser();
      router.replace(user ? landingForRole(user.role) : "/login");
    }

    void resolveLanding();
    return () => {
      cancelled = true;
    };
  }, [router]);

  return (
    <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground">
      Loading…
    </div>
  );
}
