import type { ModelTier } from "@/types/api";
import { getJson, jsonBody } from "@/api/http";

const BASE = "/api";

export interface SystemConfig {
  default_model_tier: ModelTier;
  truncate_token_threshold: number;
}

export async function fetchSystemConfig(): Promise<SystemConfig> {
  return getJson(`${BASE}/system/config`, "Failed to fetch system config");
}

/**
 * Ask the backend to open the given URL in the host OS's default browser.
 * Only http(s) URLs are honoured server-side.
 */
export async function openExternalUrl(url: string): Promise<void> {
  await fetch(`${BASE}/system/open-url`, jsonBody({ url }));
}
