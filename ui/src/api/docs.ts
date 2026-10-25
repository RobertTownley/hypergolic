import { getJson } from "@/api/http";

const BASE = "/api";

export interface DocEntry {
  slug: string;
  title: string;
  filename: string;
}

export interface DocContent {
  slug: string;
  title: string;
  content: string;
}

export async function fetchDocsList(): Promise<DocEntry[]> {
  return getJson(`${BASE}/docs/list`, "Failed to fetch docs list");
}

export async function fetchDocContent(slug: string): Promise<DocContent> {
  return getJson(`${BASE}/docs/read/${encodeURIComponent(slug)}`, "Failed to fetch doc");
}
