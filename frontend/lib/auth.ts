import type { UserPublic, UserRole } from "./types";

const USER_KEY = "platform_user";

export function getUser(): UserPublic | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as UserPublic;
  } catch {
    return null;
  }
}

export function setSession(_token: string | null, user: UserPublic): void {
  window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  window.localStorage.removeItem("platform_token");
}

export function clearSession(): void {
  window.localStorage.removeItem(USER_KEY);
  window.localStorage.removeItem("platform_token");
}

export async function refreshCurrentUser(): Promise<UserPublic | null> {
  if (typeof window === "undefined") return null;

  const response = await fetch("/api/auth/me", {
    credentials: "same-origin",
    cache: "no-store",
  });

  if (response.status === 401) {
    clearSession();
    return null;
  }
  if (!response.ok) {
    throw new Error(`unable to resolve current user: ${response.status}`);
  }

  const user = (await response.json()) as UserPublic;
  setSession(null, user);
  return user;
}

export async function logoutSession(): Promise<void> {
  if (typeof window === "undefined") return;
  try {
    await fetch("/api/auth/logout", {
      method: "POST",
      credentials: "same-origin",
    });
  } finally {
    clearSession();
  }
}

export function landingForRole(role: UserRole): string {
  switch (role) {
    case "admin":
      return "/admin";
    case "developer":
      return "/dev";
    case "user":
      return "/app";
  }
}
