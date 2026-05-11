import { apiFetch } from "./api";
import type { BootstrapState } from "./types";

export async function fetchBootstrapState(): Promise<BootstrapState> {
  return apiFetch<BootstrapState>("/bootstrap/state", { cache: "no-store" });
}
