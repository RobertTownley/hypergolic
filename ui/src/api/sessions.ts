import type {
  Session,
  SessionContext,
  ConcludePreview,
  Message,
  ModelTier,
  ContentBlock,
  PromptPartInfo,
  RoleInfo,
  SkillInfo,
  WorkflowInfo,
} from "@/types/api";
import { getJson, request, jsonBody } from "@/api/http";

const BASE = "/api";

export async function fetchSessions(projectId?: string): Promise<Session[]> {
  const qs = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return getJson(`${BASE}/sessions${qs}`, "Failed to fetch sessions");
}

export async function createSession(
  projectId: string,
  baseBranch: string,
  modelTier: ModelTier = "High",
  role: string = "generalist",
): Promise<Session> {
  return getJson(`${BASE}/sessions`, "Failed to create session", jsonBody({
      model_tier: modelTier,
      project_id: projectId,
      role,
      base_branch: baseBranch,
    }));
}

export async function forkSession(sessionId: string, withWorkspace = false): Promise<Session> {
  return getJson(`${BASE}/sessions/${sessionId}/fork`, "Failed to fork session", jsonBody({ with_workspace: withWorkspace }));
}

export async function deleteSession(sessionId: string): Promise<void> {
  await request(`${BASE}/sessions/${sessionId}`, "Failed to delete session", { method: "DELETE" });
}

export async function fetchMessages(sessionId: string): Promise<Message[]> {
  return getJson(`${BASE}/sessions/${sessionId}/messages`, "Failed to fetch messages");
}

export async function uploadAttachment(file: File): Promise<ContentBlock> {
  const formData = new FormData();
  formData.append("file", file);
  return getJson(`${BASE}/attachments/upload`, "Upload failed", { method: "POST", body: formData });
}

export async function fetchRoles(projectId?: string): Promise<RoleInfo[]> {
  const qs = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return getJson(`${BASE}/sessions/roles${qs}`, "Failed to fetch roles");
}

export async function fetchSessionSkills(sessionId: string): Promise<SkillInfo[]> {
  return getJson(`${BASE}/sessions/${sessionId}/skills`, "Failed to fetch skills");
}

export async function fetchWorkflows(sessionId: string): Promise<WorkflowInfo[]> {
  return getJson(`${BASE}/sessions/${sessionId}/workflows`, "Failed to fetch workflows");
}


export async function fetchSessionPrompt(sessionId: string): Promise<PromptPartInfo[]> {
  return getJson(`${BASE}/sessions/${sessionId}/prompt`, "Failed to fetch prompt");
}



export type { SessionContext };

export async function fetchSessionContext(sessionId: string): Promise<SessionContext> {
  return getJson(`${BASE}/sessions/${sessionId}/context`, "Failed to fetch session context");
}

export async function fetchConcludePreview(sessionId: string): Promise<ConcludePreview> {
  return getJson(`${BASE}/sessions/${sessionId}/conclude-preview`, "Failed to fetch conclude preview");
}
