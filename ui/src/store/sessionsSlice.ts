import { createSlice, createAsyncThunk, type PayloadAction } from "@reduxjs/toolkit";
import type { Session, SessionContext, SessionStatus, ModelTier } from "@/types/api";
import * as api from "@/api/sessions";
import { dedupeCondition } from "@/store/dedupeThunk";
import { setAll } from "@/store/entities";

interface SessionsState {
  entities: Record<string, Session>;
  ids: string[];
  activeSessionId: string | null;
  initialized: boolean;
  loading: boolean;
  error: string | null;
  contextBySessionId: Record<string, SessionContext>;
  concludeErrorBySessionId: Record<string, string | null>;
}

const ACTION_REQUIRED_STATUSES: Set<SessionStatus> = new Set([
  "awaiting_approval",
  "error",
]);

const BUSY_STATUSES: Set<SessionStatus> = new Set([
  "thinking",
  "streaming",
  "retrying",
  "tool_use",
  "truncating",
]);

const TERMINAL_STATUSES: Set<SessionStatus> = new Set([
  "concluded",
  "interrupted",
]);

function sessionSortKey(session: Session, activeSessionId: string | null): number {
  if (session.id === activeSessionId) return 0;
  if (ACTION_REQUIRED_STATUSES.has(session.status)) return 1;
  if (BUSY_STATUSES.has(session.status)) return 2;
  if (TERMINAL_STATUSES.has(session.status)) return 4;
  return 3;
}

function sortSessionIds(ids: string[], entities: Record<string, Session>, activeSessionId: string | null): string[] {
  return [...ids].sort((a, b) => {
    const sa = entities[a];
    const sb = entities[b];
    if (!sa || !sb) return 0;

    const tierA = sessionSortKey(sa, activeSessionId);
    const tierB = sessionSortKey(sb, activeSessionId);
    if (tierA !== tierB) return tierA - tierB;

    return new Date(sb.updated_at).getTime() - new Date(sa.updated_at).getTime();
  });
}

const initialState: SessionsState = {
  entities: {},
  ids: [],
  activeSessionId: null,
  initialized: false,
  loading: false,
  error: null,
  contextBySessionId: {},
  concludeErrorBySessionId: {},
};

export const loadSessions = createAsyncThunk(
  "sessions/load",
  async (projectId?: string) => {
    return api.fetchSessions(projectId);
  },
  { condition: dedupeCondition("sessions/load") },
);

export const addSession = createAsyncThunk(
  "sessions/add",
  async ({
    projectId,
    baseBranch,
    modelTier = "High",
    role = "generalist",
  }: {
    projectId: string;
    baseBranch: string;
    modelTier?: ModelTier;
    role?: string;
  }) => {
    return api.createSession(projectId, baseBranch, modelTier, role);
  },
);

export const removeSession = createAsyncThunk(
  "sessions/remove",
  async (sessionId: string, { dispatch }) => {
    await api.deleteSession(sessionId);
    dispatch(loadSessions());
    return sessionId;
  },
);

export const loadSessionContext = createAsyncThunk(
  "sessions/loadContext",
  async (sessionId: string) => {
    const context = await api.fetchSessionContext(sessionId);
    return { sessionId, context };
  },
);

const sessionsSlice = createSlice({
  name: "sessions",
  initialState,
  reducers: {
    setActiveSession(state, action: PayloadAction<string | null>) {
      state.activeSessionId = action.payload;
      state.ids = sortSessionIds(state.ids, state.entities, action.payload);
    },
    updateSessionStatus(state, action: PayloadAction<{ sessionId: string; status: SessionStatus; concludedAt?: string }>) {
      const { sessionId, status, concludedAt } = action.payload;
      if (state.entities[sessionId]) {
        state.entities[sessionId].status = status;
        if (concludedAt) state.entities[sessionId].concluded_at = concludedAt;
        state.entities[sessionId].updated_at = new Date().toISOString();
        state.ids = sortSessionIds(state.ids, state.entities, state.activeSessionId);
      }
    },
    updateSessionWorkflow(state, action: PayloadAction<{
      sessionId: string;
      workflowId: string | null;
      workflowName: string | null;
      workflowStateId: string | null;
      workflowStateName: string | null;
    }>) {
      const { sessionId, workflowId, workflowName, workflowStateId, workflowStateName } = action.payload;
      if (state.entities[sessionId]) {
        state.entities[sessionId].workflow_id = workflowId;
        state.entities[sessionId].workflow_name = workflowName;
        state.entities[sessionId].workflow_state_id = workflowStateId;
        state.entities[sessionId].workflow_state_name = workflowStateName;
      }
    },
    upsertSession(state, action: PayloadAction<Session>) {
      const session = action.payload;
      const isNew = !state.entities[session.id];
      state.entities[session.id] = session;
      if (isNew) {
        state.ids.push(session.id);
      }
      state.ids = sortSessionIds(state.ids, state.entities, state.activeSessionId);
    },
    updateSessionDescription(state, action: PayloadAction<{ sessionId: string; description: string }>) {
      const { sessionId, description } = action.payload;
      if (state.entities[sessionId]) {
        state.entities[sessionId].description = description;
      }
    },
    concludeSession(state, action: PayloadAction<{ sessionId: string; rating: number; feedback: string | null; concludedAt: string | null }>) {
      const { sessionId, rating, feedback, concludedAt } = action.payload;
      if (state.entities[sessionId]) {
        state.entities[sessionId].conclusion_rating = rating;
        state.entities[sessionId].conclusion_feedback = feedback;
        state.entities[sessionId].concluded_at = concludedAt;
      }
      delete state.concludeErrorBySessionId[sessionId];
    },
    setConcludeError(state, action: PayloadAction<{ sessionId: string; detail: string }>) {
      state.concludeErrorBySessionId[action.payload.sessionId] = action.payload.detail;
    },
    clearConcludeError(state, action: PayloadAction<string>) {
      delete state.concludeErrorBySessionId[action.payload];
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(loadSessions.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(loadSessions.fulfilled, (state, action) => {
        state.loading = false;
        state.initialized = true;
        setAll(state, action.payload);
        state.ids = sortSessionIds(state.ids, state.entities, state.activeSessionId);
      })
      .addCase(loadSessions.rejected, (state, action) => {
        state.loading = false;
        state.initialized = true;
        state.error = action.error.message ?? "Failed to load sessions";
      })
      .addCase(addSession.fulfilled, (state, action) => {
        const session = action.payload;
        state.entities[session.id] = session;
        state.ids.unshift(session.id);
        // Intentionally do NOT set activeSessionId here. Callers are required
        // to dispatch setActiveSession(id) after awaiting this thunk, so that
        // focusListener observes a real prev->next transition and fans out the
        // workspace loads. If we mutated activeSessionId inline, the listener's
        // originalState.activeSessionId would already equal the new id and the
        // prev===next guard would short-circuit the fan-out.
      })
      .addCase(removeSession.fulfilled, (state, action) => {
        const id = action.payload;
        delete state.entities[id];
        delete state.contextBySessionId[id];
        delete state.concludeErrorBySessionId[id];
        state.ids = state.ids.filter((i) => i !== id);
        if (state.activeSessionId === id) {
          // Don't advance here — focusListener watches removeSession.fulfilled
          // and dispatches setActiveSession(next) so the workspaceSlice mirror
          // and the workspace load fan-out both trigger off a real action.
          state.activeSessionId = null;
        }
      })
      .addCase(loadSessionContext.fulfilled, (state, action) => {
        const { sessionId, context } = action.payload;
        state.contextBySessionId[sessionId] = context;
      });
  },
});

export const selectConcludeError = (state: { sessions: SessionsState }, sessionId: string | null): string | null =>
  sessionId ? state.sessions.concludeErrorBySessionId[sessionId] ?? null : null;

export const { setActiveSession, updateSessionStatus, updateSessionWorkflow, upsertSession, updateSessionDescription, concludeSession, setConcludeError, clearConcludeError } = sessionsSlice.actions;
export default sessionsSlice.reducer;
