import type { Project } from "@/types/api";
import { getJson } from "@/api/http";

const BASE = "/api";

export async function fetchProjects(): Promise<Project[]> {
  return getJson(`${BASE}/projects`, "Failed to fetch projects");
}

export interface ProjectBranchesResponse {
  project_id: string;
  branches: string[];
  current: string;
}

// Project-scoped branch listing — used before a session exists so we
// can pick a default base branch. The session-scoped /api/git/branches
// endpoint requires a session_id.
export async function fetchProjectBranches(projectId: string): Promise<ProjectBranchesResponse> {
  return getJson(`${BASE}/projects/${encodeURIComponent(projectId)}/branches`, "Failed to fetch project branches");
}
