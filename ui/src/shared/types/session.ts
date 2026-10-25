import type { ToolInfo } from "./tools";

export type ModelTier = "Low" | "Medium" | "High" | "Extra High";

export type SessionStatus =
  | "idle"
  | "thinking"
  | "streaming"
  | "retrying"
  | "tool_use"
  | "truncating"
  | "awaiting_approval"
  | "error"
  | "concluding"
  | "concluded"
  | "interrupted";

export interface SessionContext {
  tools: ToolInfo[];
  tools_count: number;
  tools_token_estimate: number;
  skills_summary: { total: number; activated: string[] };
  mcp_enabled: string[];
  prompt_token_estimate: number;
}

export interface Session {
  id: string;
  model_tier: ModelTier;
  project_id: string;
  project_name: string;
  role: string;
  status: SessionStatus;
  created_at: string;
  updated_at: string;
  message_count: number;
  workflow_id: string | null;
  workflow_name: string | null;
  workflow_state_id: string | null;
  workflow_state_name: string | null;
  parent_id: string | null;
  description: string | null;
  conclusion_rating: number | null;
  conclusion_feedback: string | null;
  concluded_at: string | null;
  worktree_path?: string | null;
  worktree_branch?: string | null;
  base_branch?: string | null;
  worktree_status?:
    | "pending"
    | "creating"
    | "starting_sandbox"
    | "cloning"
    | "seeding"
    | "ready"
    | "create_failed"
    | "seed_failed"
    | null;
  context?: SessionContext | null;
}

export interface ConcludePreview {
  is_worktree_session: boolean;
  branch_has_unmerged_commits: boolean;
  unmerged_count: number;
}
