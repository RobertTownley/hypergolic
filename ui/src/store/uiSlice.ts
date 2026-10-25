import { createSlice, createAsyncThunk, PayloadAction } from "@reduxjs/toolkit";
import type { CodeSelectionAttachment, CodeSelection, FileAttachment, ModelTier, SummaryRecallAttachment } from "@/types/api";
import { fetchSystemConfig } from "@/api/system";
import { FALLBACK_TRUNCATION_THRESHOLD } from "@/activity/constants";
import { setActiveSession, concludeSession } from "@/store/sessionsSlice";

export type LeftTab = "chat" | "sessions" | "git" | "files" | "help" | "projects" | "analytics" | "harness";

let codeSelectionIdCounter = 0;
let summaryRecallIdCounter = 0;

export interface SessionDraft {
  text: string;
  fileAttachments: FileAttachment[];
  codeSelections: CodeSelectionAttachment[];
  summaryRecalls: SummaryRecallAttachment[];
  workflowId: string | null;
}

const emptyDraft: SessionDraft = {
  text: "",
  fileAttachments: [],
  codeSelections: [],
  summaryRecalls: [],
  workflowId: null,
};

export interface ConcludeDraft {
  rating: number;
  feedback: string;
  deleteWorktree: boolean;
  deleteBranch: boolean;
  analyzeLearnings: boolean;
}

const emptyConcludeDraft: ConcludeDraft = {
  rating: 3,
  feedback: "",
  deleteWorktree: true,
  deleteBranch: true,
  analyzeLearnings: false,
};

export const loadSystemConfig = createAsyncThunk(
  "ui/loadSystemConfig",
  async () => fetchSystemConfig(),
);

interface UIState {
  leftTab: LeftTab;
  leftPanelCollapsed: boolean;
  rightPanelCollapsed: boolean;
  drafts: Record<string, SessionDraft>;
  concludeDrafts: Record<string, ConcludeDraft>;
  mountedTerminalSessions: string[];
  defaultModelTier: ModelTier | null;
  truncationThreshold: number | null;
}

const initialState: UIState = {
  leftTab: "git",
  leftPanelCollapsed: false,
  rightPanelCollapsed: false,
  drafts: {},
  concludeDrafts: {},
  mountedTerminalSessions: [],
  defaultModelTier: null,
  truncationThreshold: null,
};

function ensureDraft(state: UIState, sessionId: string): SessionDraft {
  if (!state.drafts[sessionId]) {
    state.drafts[sessionId] = { ...emptyDraft, fileAttachments: [], codeSelections: [], summaryRecalls: [] };
  }
  return state.drafts[sessionId];
}

const uiSlice = createSlice({
  name: "ui",
  initialState,
  extraReducers: (builder) => {
    builder.addCase(loadSystemConfig.fulfilled, (state, action) => {
      state.defaultModelTier = action.payload.default_model_tier;
      state.truncationThreshold = action.payload.truncate_token_threshold;
    });
    builder.addCase(setActiveSession, (state, action) => {
      if (action.payload) state.leftTab = "git";
    });
    // concludeSession fires only on server-confirmed conclude; a
    // conclude_error leaves the draft intact so the re-opened modal
    // restores the user's rating/feedback/flags.
    builder.addCase(concludeSession, (state, action) => {
      delete state.concludeDrafts[action.payload.sessionId];
    });
  },
  reducers: {
    setLeftTab(state, action: PayloadAction<LeftTab>) {
      state.leftTab = action.payload;
    },
    toggleLeftPanel(state) {
      state.leftPanelCollapsed = !state.leftPanelCollapsed;
    },
    setLeftPanelCollapsed(state, action: PayloadAction<boolean>) {
      state.leftPanelCollapsed = action.payload;
    },
    toggleRightPanel(state) {
      state.rightPanelCollapsed = !state.rightPanelCollapsed;
    },
    setDraftText(state, action: PayloadAction<{ sessionId: string; text: string }>) {
      ensureDraft(state, action.payload.sessionId).text = action.payload.text;
    },
    setDraftWorkflow(state, action: PayloadAction<{ sessionId: string; workflowId: string | null }>) {
      ensureDraft(state, action.payload.sessionId).workflowId = action.payload.workflowId;
    },
    setDraftFileAttachments(state, action: PayloadAction<{ sessionId: string; attachments: FileAttachment[] }>) {
      ensureDraft(state, action.payload.sessionId).fileAttachments = action.payload.attachments;
    },
    addDraftCodeSelection(state, action: PayloadAction<{ sessionId: string; selection: CodeSelection }>) {
      const draft = ensureDraft(state, action.payload.sessionId);
      draft.codeSelections.push({
        id: `code-sel-${++codeSelectionIdCounter}`,
        type: "code_selection",
        selection: action.payload.selection,
      });
    },
    addDraftSummaryRecall(
      state,
      action: PayloadAction<{ sessionId: string; summaryId: string; content: string }>,
    ) {
      const draft = ensureDraft(state, action.payload.sessionId);
      if (draft.summaryRecalls.some((a) => a.summaryId === action.payload.summaryId)) return;
      draft.summaryRecalls.push({
        id: `summary-recall-${++summaryRecallIdCounter}`,
        type: "summary_recall",
        summaryId: action.payload.summaryId,
        content: action.payload.content,
      });
    },
    removeDraftSummaryRecall(state, action: PayloadAction<{ sessionId: string; id: string }>) {
      const draft = ensureDraft(state, action.payload.sessionId);
      draft.summaryRecalls = draft.summaryRecalls.filter((a) => a.id !== action.payload.id);
    },
    removeDraftCodeSelection(state, action: PayloadAction<{ sessionId: string; id: string }>) {
      const draft = state.drafts[action.payload.sessionId];
      if (draft) {
        draft.codeSelections = draft.codeSelections.filter(
          (s) => s.id !== action.payload.id,
        );
      }
    },
    clearDraft(state, action: PayloadAction<string>) {
      delete state.drafts[action.payload];
    },
    setConcludeDraft(state, action: PayloadAction<{ sessionId: string } & Partial<ConcludeDraft>>) {
      const { sessionId, ...patch } = action.payload;
      state.concludeDrafts[sessionId] = {
        ...(state.concludeDrafts[sessionId] ?? emptyConcludeDraft),
        ...patch,
      };
    },
    mountTerminalSession(state, action: PayloadAction<string>) {
      if (!state.mountedTerminalSessions.includes(action.payload)) {
        state.mountedTerminalSessions.push(action.payload);
      }
    },
    unmountTerminalSession(state, action: PayloadAction<string>) {
      state.mountedTerminalSessions = state.mountedTerminalSessions.filter(
        (id) => id !== action.payload,
      );
    },
  },
});

export const selectDefaultModelTier = (state: { ui: UIState }): ModelTier =>
  state.ui.defaultModelTier ?? "High";

export const selectTruncationThreshold = (state: { ui: UIState }): number =>
  state.ui.truncationThreshold ?? FALLBACK_TRUNCATION_THRESHOLD;

export const selectDraft = (state: { ui: UIState }, sessionId: string | null): SessionDraft => {
  if (!sessionId) return emptyDraft;
  return state.ui.drafts[sessionId] ?? emptyDraft;
};

export const selectConcludeDraft = (state: { ui: UIState }, sessionId: string | null): ConcludeDraft => {
  if (!sessionId) return emptyConcludeDraft;
  return state.ui.concludeDrafts[sessionId] ?? emptyConcludeDraft;
};

export const {
  setLeftTab,
  toggleLeftPanel,
  setLeftPanelCollapsed,
  toggleRightPanel,
  setDraftText,
  setDraftWorkflow,
  setDraftFileAttachments,
  addDraftCodeSelection,
  addDraftSummaryRecall,
  removeDraftSummaryRecall,
  removeDraftCodeSelection,
  clearDraft,
  setConcludeDraft,
  mountTerminalSession,
  unmountTerminalSession,
} = uiSlice.actions;
export default uiSlice.reducer;
