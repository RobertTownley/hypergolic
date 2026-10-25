import type { ContentBlock, UsageInfo } from "./message";
import type { Session, SessionStatus } from "./session";
import type { GitStatusResponse } from "./git";

// A resolved approval-view block. The backend resolves field references
// against the tool input and ships plain values here; the UI is a pure
// renderer. See hypergolic/tools/approval_view.py for the authoring side.
export type ResolvedBlock =
  | ResolvedCodeBlock
  | ResolvedMarkdownBlock
  | ResolvedTextBlock
  | ResolvedBadgeBlock
  | ResolvedForEachBlock;

export interface ResolvedCodeBlock {
  type: "code";
  value: string;
  language: string;
  label: string | null;
  max_height: string | number;
}

export interface ResolvedMarkdownBlock {
  type: "markdown";
  value: string;
  label: string | null;
}

export interface ResolvedTextBlock {
  type: "text";
  value: string;
  label: string | null;
  mono: boolean;
}

export interface ResolvedBadgeBlock {
  type: "badge";
  value: string;
  label: string | null;
  tone: "neutral" | "warn" | "danger" | "info";
}

interface ResolvedForEachItem {
  heading: string | null;
  blocks: ResolvedBlock[];
}

export interface ResolvedForEachBlock {
  type: "for_each";
  label: string | null;
  separator: "divider" | "gap" | "none";
  empty_text: string | null;
  items: ResolvedForEachItem[];
}

export interface ResolvedApprovalView {
  blocks: ResolvedBlock[];
  show_raw_json: boolean;
}

interface WsAssistantMessage {
  type: "assistant_message";
  role: "assistant";
  content: ContentBlock[];
  session_id: string;
  model?: string;
  stop_reason?: string;
  message_id?: string;
  usage?: UsageInfo;
}

interface WsToolResult {
  type: "tool_result";
  role: "user";
  content: ContentBlock[];
  session_id: string;
}

/** Live output from a running exec, correlated to its pending call card. */
interface WsToolOutputChunk {
  type: "tool_output_chunk";
  content: { tool_use_id: string; stream: "stdout" | "stderr"; text: string }[];
  session_id: string;
}

export interface WsDone {
  type: "done";
  session_id: string;
  git_status?: GitStatusResponse;
}

export interface WsError {
  type: "error";
  detail: string;
  session_id?: string;
}

export interface WsInterrupted {
  type: "interrupted";
  session_id?: string;
  partial_text?: string;
}

interface WsContentBlockStart {
  type: "content_block_start";
  role: "assistant";
  content: [{
    type: string;
    index: number;
    text?: string;
    thinking?: string;
    id?: string;
    name?: string;
    display_name?: string;
    input?: Record<string, unknown>;
  }];
  session_id: string;
}

interface WsContentBlockDelta {
  type: "content_block_delta";
  role: "assistant";
  content: [{
    type: string;
    index: number;
    text?: string;
    thinking?: string;
    partial_json?: string;
  }];
  session_id: string;
}

interface WsContentBlockStop {
  type: "content_block_stop";
  role: "assistant";
  content: [{ index: number }];
  session_id: string;
}

interface WsToolApprovalRequest {
  type: "tool_approval_request";
  tool_use_id: string;
  tool_name: string;
  tool_display_name?: string;
  tool_input: Record<string, unknown>;
  session_id: string;
  approval_view?: ResolvedApprovalView;
}

export interface WsSessionStatusChange {
  type: "session_status_change";
  session_id: string;
  content: [{ status: SessionStatus; concluded_at?: string }];
}

interface WsTruncated {
  type: "truncated";
  session_id: string;
}

interface WsWorkflowStateChange {
  type: "workflow_state_change";
  session_id: string;
  content: [{
    workflow_id: string | null;
    workflow_name: string | null;
    workflow_state_id: string | null;
    workflow_state_name: string | null;
  }];
}

export interface WsDispatchStarted {
  type: "dispatch_started";
  session_id: string;
  role: "system";
  content: [{ child_session_id: string; child_session?: Session }];
}

interface WsDispatchConcluded {
  type: "dispatch_concluded";
  session_id: string;
  role: "system";
  content: [];
}

interface WsSessionDescriptionUpdate {
  type: "session_description_update";
  session_id: string;
  role: "system";
  content: [{ description: string }];
}

export interface WsSessionConcluded {
  type: "session_concluded";
  session_id: string;
  conclusion_rating: number;
  conclusion_feedback: string | null;
  concluded_at: string | null;
}

export interface WsSandboxStatusChange {
  type: "sandbox_status_change";
  session_id: string;
  role: "system";
  content: [{ status: "running" }];
}

interface WsConcludeError {
  type: "conclude_error";
  session_id: string;
  detail: string;
}

export type WsEvent =
  | WsAssistantMessage
  | WsToolResult
  | WsToolOutputChunk
  | WsDone
  | WsError
  | WsInterrupted
  | WsContentBlockStart
  | WsContentBlockDelta
  | WsContentBlockStop
  | WsToolApprovalRequest
  | WsSessionStatusChange
  | WsTruncated
  | WsWorkflowStateChange
  | WsDispatchStarted
  | WsDispatchConcluded
  | WsSessionDescriptionUpdate
  | WsSessionConcluded
  | WsSandboxStatusChange
  | WsConcludeError;
