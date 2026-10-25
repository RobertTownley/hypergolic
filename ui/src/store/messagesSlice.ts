import { createSlice, createAsyncThunk, type PayloadAction } from "@reduxjs/toolkit";
import type { Message, ContentBlock, UsageInfo, ResolvedApprovalView } from "@/types/api";
import * as api from "@/api/sessions";
import { removeSession } from "@/store/sessionsSlice";

export interface StreamingBlock {
  type: string;
  text?: string;
  thinking?: string;
  id?: string;
  name?: string;
  display_name?: string;
  partialJson?: string;
  /** Epoch ms the block began streaming; a tool call's "writing" clock. */
  startedAt?: number;
}

export interface PendingApproval {
  toolUseId: string;
  toolName: string;
  toolId: string;
  toolInput: Record<string, unknown>;
  sessionId: string;
  approvalView?: ResolvedApprovalView;
}

interface MessagesState {
  bySessionId: Record<string, Message[]>;
  loadingSessionIds: Record<string, boolean>;
  loadedSessionIds: Record<string, boolean>;
  streaming: boolean;
  streamingSessions: Record<string, boolean>;
  streamingBlocksBySessionId: Record<string, StreamingBlock[]>;
  errorBySessionId: Record<string, string>;
  pendingApprovalBySession: Record<string, PendingApproval[]>;
  liveToolOutputByToolUseId: Record<string, string>;
}

const initialState: MessagesState = {
  bySessionId: {},
  loadingSessionIds: {},
  loadedSessionIds: {},
  streaming: false,
  streamingSessions: {},
  streamingBlocksBySessionId: {},
  errorBySessionId: {},
  pendingApprovalBySession: {},
  liveToolOutputByToolUseId: {},
};

export const loadMessages = createAsyncThunk(
  "messages/load",
  async (sessionId: string) => {
    const fetchedAt = new Date().toISOString();
    const messages = await api.fetchMessages(sessionId);
    return { sessionId, messages, fetchedAt };
  },
  {
    condition: (sessionId, { getState }) => {
      const state = getState() as { messages: MessagesState };
      // Don't load if already loading
      if (state.messages.loadingSessionIds[sessionId]) {
        return false;
      }
      return true;
    },
  },
);

const messagesSlice = createSlice({
  name: "messages",
  initialState,
  reducers: {
    setSessionStreaming(state, action: PayloadAction<{ sessionId: string; streaming: boolean }>) {
      const { sessionId, streaming } = action.payload;
      if (streaming) {
        state.streamingSessions[sessionId] = true;
      } else {
        delete state.streamingSessions[sessionId];
      }
      state.streaming = Object.keys(state.streamingSessions).length > 0;
    },
    setSessionError(state, action: PayloadAction<{ sessionId: string; error: string | null }>) {
      const { sessionId, error } = action.payload;
      if (error) {
        state.errorBySessionId[sessionId] = error;
      } else {
        delete state.errorBySessionId[sessionId];
      }
    },
    addUserMessage(
      state,
      action: PayloadAction<{ sessionId: string; text: string; contentBlocks?: ContentBlock[] }>
    ) {
      const { sessionId, text, contentBlocks } = action.payload;
      if (!state.bySessionId[sessionId]) {
        state.bySessionId[sessionId] = [];
      }
      const content: ContentBlock[] = [
        ...(contentBlocks ?? []),
        { type: "text", text },
      ];
      state.bySessionId[sessionId].push({
        id: `user-${Date.now()}`,
        session_id: sessionId,
        role: "user",
        content,
        created_at: new Date().toISOString(),
      });
    },
    addAssistantMessage(
      state,
      action: PayloadAction<{
        sessionId: string;
        content: ContentBlock[];
        model?: string;
        stopReason?: string;
        messageId?: string;
        usage?: UsageInfo;
      }>
    ) {
      const { sessionId, content, model, stopReason, messageId, usage } = action.payload;
      if (!state.bySessionId[sessionId]) {
        state.bySessionId[sessionId] = [];
      }
      state.bySessionId[sessionId].push({
        id: messageId ?? `assistant-${Date.now()}`,
        session_id: sessionId,
        role: "assistant",
        content,
        model,
        stop_reason: stopReason,
        usage,
        created_at: new Date().toISOString(),
      });
    },
    appendToolOutput(state, action: PayloadAction<{ toolUseId: string; text: string }>) {
      const { toolUseId, text } = action.payload;
      const prev = state.liveToolOutputByToolUseId[toolUseId] ?? "";
      state.liveToolOutputByToolUseId[toolUseId] = (prev + text).slice(-4000);
      const ids = Object.keys(state.liveToolOutputByToolUseId);
      for (const id of ids.slice(0, Math.max(0, ids.length - 32))) {
        delete state.liveToolOutputByToolUseId[id];
      }
    },
    addToolResult(
      state,
      action: PayloadAction<{
        sessionId: string;
        content: ContentBlock[];
      }>
    ) {
      const { sessionId, content } = action.payload;
      for (const block of content) {
        if (block.tool_use_id) delete state.liveToolOutputByToolUseId[block.tool_use_id];
      }
      if (!state.bySessionId[sessionId]) {
        state.bySessionId[sessionId] = [];
      }
      state.bySessionId[sessionId].push({
        id: `tool-result-${Date.now()}`,
        session_id: sessionId,
        role: "user",
        content,
        created_at: new Date().toISOString(),
      });
    },
    startContentBlock(
      state,
      action: PayloadAction<{
        sessionId: string;
        index: number;
        blockType: string;
        id?: string;
        name?: string;
        display_name?: string;
        startedAt?: number;
      }>
    ) {
      const { sessionId, index, blockType, id, name, display_name, startedAt } = action.payload;
      if (!state.streamingBlocksBySessionId[sessionId]) {
        state.streamingBlocksBySessionId[sessionId] = [];
      }
      state.streamingBlocksBySessionId[sessionId][index] = {
        type: blockType,
        text: blockType === "text" ? "" : undefined,
        thinking: blockType === "thinking" ? "" : undefined,
        id,
        name,
        display_name,
        startedAt,
        partialJson: blockType === "tool_call" || blockType === "tool_use" ? "" : undefined,
      };
    },
    appendContentDelta(
      state,
      action: PayloadAction<{
        sessionId: string;
        index: number;
        text?: string;
        thinking?: string;
        partialJson?: string;
      }>
    ) {
      const { sessionId, index, text, thinking, partialJson } = action.payload;
      const blocks = state.streamingBlocksBySessionId[sessionId];
      if (!blocks) return;
      const block = blocks[index];
      if (!block) return;
      if (text !== undefined && block.text !== undefined) {
        block.text += text;
      }
      if (thinking !== undefined && block.thinking !== undefined) {
        block.thinking += thinking;
      }
      if (partialJson !== undefined && block.partialJson !== undefined) {
        block.partialJson += partialJson;
      }
    },
    clearStreamingContent(state, action: PayloadAction<string>) {
      delete state.streamingBlocksBySessionId[action.payload];
    },
    setPendingApproval(state, action: PayloadAction<PendingApproval | null>) {
      if (action.payload) {
        const sid = action.payload.sessionId;
        if (!state.pendingApprovalBySession[sid]) {
          state.pendingApprovalBySession[sid] = [];
        }
        state.pendingApprovalBySession[sid].push(action.payload);
      }
    },
    clearPendingApproval(state, action: PayloadAction<{ sessionId: string; toolUseId: string }>) {
      const { sessionId, toolUseId } = action.payload;
      const queue = state.pendingApprovalBySession[sessionId];
      if (queue) {
        state.pendingApprovalBySession[sessionId] = queue.filter(a => a.toolUseId !== toolUseId);
        if (state.pendingApprovalBySession[sessionId].length === 0) {
          delete state.pendingApprovalBySession[sessionId];
        }
      }
    },
    clearAllPendingApprovals(state, action: PayloadAction<string>) {
      delete state.pendingApprovalBySession[action.payload];
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(loadMessages.pending, (state, action) => {
        state.loadingSessionIds[action.meta.arg] = true;
      })
      .addCase(loadMessages.fulfilled, (state, action) => {
        const { sessionId, messages, fetchedAt } = action.payload;
        // Keep optimistic user messages the fetch couldn't have seen: a send
        // racing an interrupt/error-triggered reload must not lose its bubble.
        // The next reload includes the persisted copy and drops these.
        const optimistic = (state.bySessionId[sessionId] ?? []).filter(
          (m) => m.id.startsWith("user-") && m.created_at > fetchedAt,
        );
        state.bySessionId[sessionId] = [...messages, ...optimistic];
        state.loadedSessionIds[sessionId] = true;
        delete state.loadingSessionIds[sessionId];
        delete state.errorBySessionId[sessionId];
      })
      .addCase(loadMessages.rejected, (state, action) => {
        delete state.loadingSessionIds[action.meta.arg];
      })
      .addCase(removeSession.fulfilled, (state, action) => {
        delete state.bySessionId[action.payload];
        delete state.loadedSessionIds[action.payload];
        delete state.errorBySessionId[action.payload];
        delete state.pendingApprovalBySession[action.payload];
        delete state.streamingSessions[action.payload];
        delete state.streamingBlocksBySessionId[action.payload];
      });
  },
});

export const {
  setSessionStreaming,
  setSessionError,
  addUserMessage,
  addAssistantMessage,
  addToolResult,
  appendToolOutput,
  startContentBlock,
  appendContentDelta,
  clearStreamingContent,
  setPendingApproval,
  clearPendingApproval,
  clearAllPendingApprovals,
} = messagesSlice.actions;
export default messagesSlice.reducer;
