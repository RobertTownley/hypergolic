interface ImageSource {
  type: "base64";
  media_type: string;
  data: string;
}

/** Effective context the model saw: input alone excludes cached tokens. */
export const contextOf = (u: UsageInfo) =>
  u.input_tokens + (u.cache_creation_input_tokens ?? 0) + (u.cache_read_input_tokens ?? 0);

export interface UsageInfo {
  input_tokens: number;
  output_tokens: number;
  cache_creation_input_tokens?: number;
  cache_read_input_tokens?: number;
}

export interface ContentBlock {
  type: string;
  text?: string;
  thinking?: string;
  signature?: string;
  id?: string;
  name?: string;
  display_name?: string;
  input?: Record<string, unknown>;
  tool_use_id?: string;
  content?: ContentBlock[];
  is_error?: boolean;
  source?: ImageSource;
  /** UI-only structured detail on a tool_result; never sent to the model. */
  meta?: ToolResultMeta;
}

/** See ToolResult.meta in hypergolic/harness/primitives.py. */
export interface ToolResultMeta {
  workflow_id?: string;
  workflow_name?: string;
  workflow_state_id?: string;
  workflow_state_name?: string;
}

export interface Message {
  id: string;
  session_id: string;
  role: "user" | "assistant" | "system";
  content: ContentBlock[];
  model?: string | null;
  stop_reason?: string | null;
  usage?: UsageInfo | null;
  truncated?: boolean;
  created_at: string;
}

export interface CodeSelection {
  filePath: string;
  startLine: number;
  endLine: number;
  content: string;
  language: string;
}

interface ImageAttachment {
  id: string;
  type: "image";
  source: ImageSource;
  preview: string;
  filename: string;
}

interface DocumentAttachment {
  id: string;
  type: "document";
  source: ImageSource;
  filename: string;
}

export type FileAttachment = ImageAttachment | DocumentAttachment;

export interface CodeSelectionAttachment {
  id: string;
  type: "code_selection";
  selection: CodeSelection;
}

export interface SummaryRecallAttachment {
  id: string;
  type: "summary_recall";
  /** Message id of the [Turn Summary] row this re-includes. */
  summaryId: string;
  content: string;
}

export type Attachment = FileAttachment | CodeSelectionAttachment | SummaryRecallAttachment;
