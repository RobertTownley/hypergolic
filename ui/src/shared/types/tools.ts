export interface ToolInfo {
  id: string;
  name: string;
  description: string;
  reason: string;
  requires_approval: boolean;
  token_estimate: number;
  mcp_server: string | null;
  input_schema: Record<string, unknown> | null;
  usage?: string | null;
}

export interface MCPServerInfo {
  name: string;
  source: "user" | "project";
  connected: boolean;
  tool_count: number;
  transport: "stdio" | "streamable_http" | "sse";
  auth_type: "none" | "token" | "oauth";
  auth_status: "not_required" | "ready" | "needs_oauth" | "missing_token" | "unknown";
}

export interface Annotation {
  id: string;
  highlighted_text: string;
  comment: string;
  position: number;
}
