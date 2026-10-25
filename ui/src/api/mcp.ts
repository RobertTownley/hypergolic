import type { MCPServerInfo } from "@/types/api";
import { getJson, jsonBody } from "@/api/http";

const BASE = "/api";

export async function fetchMCPServers(projectId?: string): Promise<MCPServerInfo[]> {
  const qs = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return getJson(`${BASE}/mcp/servers${qs}`, "Failed to fetch MCP servers");
}

export async function connectMCPServer(serverName: string, sessionId: string, projectId?: string): Promise<MCPServerInfo> {
  const qs = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return getJson(`${BASE}/mcp/servers/${encodeURIComponent(serverName)}/connect${qs}`, "Failed to connect MCP server", jsonBody({ session_id: sessionId }));
}

export async function disconnectMCPServer(serverName: string, sessionId: string, projectId?: string): Promise<MCPServerInfo> {
  const qs = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return getJson(`${BASE}/mcp/servers/${encodeURIComponent(serverName)}/disconnect${qs}`, "Failed to disconnect MCP server", jsonBody({ session_id: sessionId }));
}

export async function fetchSessionEnabledServers(sessionId: string): Promise<string[]> {
  return getJson(`${BASE}/mcp/sessions/${sessionId}/enabled`, "Failed to fetch enabled servers");
}


