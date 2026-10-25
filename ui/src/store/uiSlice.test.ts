import { describe, it, expect } from "vitest";
import uiReducer, {
  toggleLeftPanel,
  setDraftText,
  addDraftCodeSelection,
  removeDraftCodeSelection,
  clearDraft,
  setConcludeDraft,
  selectDraft,
  selectConcludeDraft,
} from "./uiSlice";
import type { CodeSelection } from "@/types/api";
import { setActiveSession, concludeSession } from "./sessionsSlice";

const initialState = {
  leftTab: "git" as const,
  leftPanelCollapsed: false,
  rightPanelCollapsed: false,
  drafts: {},
  concludeDrafts: {},
  mountedTerminalSessions: [] as string[],
  defaultModelTier: null,
  truncationThreshold: null,
};

type UiState = ReturnType<typeof uiReducer>;

const sampleSelection: CodeSelection = {
  filePath: "src/main.ts",
  startLine: 10,
  endLine: 20,
  content: "const x = 1;",
  language: "typescript",
};

function addSelection(state: UiState, sessionId: string, filePath = sampleSelection.filePath): UiState {
  return uiReducer(state, addDraftCodeSelection({ sessionId, selection: { ...sampleSelection, filePath } }));
}

describe("uiSlice", () => {
  it("should return the initial state", () => {
    const state = uiReducer(undefined, { type: "unknown" });
    expect(state.leftTab).toBe("git");
    expect(state.leftPanelCollapsed).toBe(false);
    expect(state.drafts).toEqual({});
  });

  describe("panel collapse", () => {
    it("toggleLeftPanel should toggle collapsed state", () => {
      let state = uiReducer(initialState, toggleLeftPanel());
      expect(state.leftPanelCollapsed).toBe(true);
      state = uiReducer(state, toggleLeftPanel());
      expect(state.leftPanelCollapsed).toBe(false);
    });
  });

  describe("session drafts", () => {
    const sid = "session-1";
    const sid2 = "session-2";

    describe("setDraftText", () => {
      it("should set text for a session, creating draft lazily", () => {
        const state = uiReducer(initialState, setDraftText({ sessionId: sid, text: "hello" }));
        expect(state.drafts[sid].text).toBe("hello");
      });

      it("should keep drafts isolated per session", () => {
        let state = uiReducer(initialState, setDraftText({ sessionId: sid, text: "hello" }));
        state = uiReducer(state, setDraftText({ sessionId: sid2, text: "world" }));
        expect(state.drafts[sid].text).toBe("hello");
        expect(state.drafts[sid2].text).toBe("world");
      });
    });

    describe("addDraftCodeSelection", () => {
      it("should add a code selection with a generated id", () => {
        const state = addSelection(initialState, sid);
        expect(state.drafts[sid].codeSelections).toHaveLength(1);
        expect(state.drafts[sid].codeSelections[0].type).toBe("code_selection");
        expect(state.drafts[sid].codeSelections[0].selection).toEqual(sampleSelection);
        expect(state.drafts[sid].codeSelections[0].id).toMatch(/^code-sel-/);
      });

      it("should accumulate multiple selections with unique ids", () => {
        const state = addSelection(addSelection(initialState, sid), sid, "other.ts");
        expect(state.drafts[sid].codeSelections).toHaveLength(2);
        const ids = state.drafts[sid].codeSelections.map((s) => s.id);
        expect(new Set(ids).size).toBe(2);
      });

      it("should keep code selections isolated per session", () => {
        const state = addSelection(addSelection(initialState, sid), sid2, "b.ts");
        expect(state.drafts[sid].codeSelections).toHaveLength(1);
        expect(state.drafts[sid2].codeSelections).toHaveLength(1);
        expect(state.drafts[sid2].codeSelections[0].selection.filePath).toBe("b.ts");
      });
    });

    describe("removeDraftCodeSelection", () => {
      it("should remove a selection by id, leaving others intact", () => {
        let state = addSelection(addSelection(initialState, sid), sid, "b.ts");
        const [first, second] = state.drafts[sid].codeSelections;
        state = uiReducer(state, removeDraftCodeSelection({ sessionId: sid, id: first.id }));
        expect(state.drafts[sid].codeSelections).toHaveLength(1);
        expect(state.drafts[sid].codeSelections[0].selection.filePath).toBe("b.ts");
        state = uiReducer(state, removeDraftCodeSelection({ sessionId: sid, id: second.id }));
        expect(state.drafts[sid].codeSelections).toHaveLength(0);
      });

      it("should noop for unknown id", () => {
        let state = addSelection(initialState, sid);
        state = uiReducer(state, removeDraftCodeSelection({ sessionId: sid, id: "nonexistent" }));
        expect(state.drafts[sid].codeSelections).toHaveLength(1);
      });
    });

    describe("clearDraft", () => {
      it("should remove entire draft for a session without affecting others", () => {
        let state = uiReducer(initialState, setDraftText({ sessionId: sid, text: "hello" }));
        state = addSelection(state, sid);
        state = uiReducer(state, setDraftText({ sessionId: sid2, text: "world" }));
        state = uiReducer(state, clearDraft(sid));
        expect(state.drafts[sid]).toBeUndefined();
        expect(state.drafts[sid2].text).toBe("world");
      });

      it("should noop on empty", () => {
        const state = uiReducer(initialState, clearDraft("nonexistent"));
        expect(state.drafts).toEqual({});
      });
    });

    describe("selectDraft", () => {
      it("should return empty draft for unknown or null session", () => {
        for (const sessionId of ["unknown", null]) {
          const draft = selectDraft({ ui: initialState }, sessionId);
          expect(draft.text).toBe("");
          expect(draft.fileAttachments).toEqual([]);
          expect(draft.codeSelections).toEqual([]);
          expect(draft.workflowId).toBeNull();
        }
      });

      it("should return existing draft", () => {
        const state = uiReducer(initialState, setDraftText({ sessionId: sid, text: "draft text" }));
        const draft = selectDraft({ ui: state }, sid);
        expect(draft.text).toBe("draft text");
      });
    });
  });

  describe("conclude drafts", () => {
    const sid = "session-1";
    const sid2 = "session-2";

    describe("setConcludeDraft", () => {
      it("should create the draft lazily with defaults and apply the patch", () => {
        const state = uiReducer(initialState, setConcludeDraft({ sessionId: sid, rating: 5 }));
        expect(state.concludeDrafts[sid]).toEqual({
          rating: 5,
          feedback: "",
          deleteWorktree: true,
          deleteBranch: true,
          analyzeLearnings: false,
        });
      });

      it("should merge successive patches", () => {
        let state = uiReducer(initialState, setConcludeDraft({ sessionId: sid, rating: 1 }));
        state = uiReducer(state, setConcludeDraft({ sessionId: sid, feedback: "notes", deleteBranch: false }));
        expect(state.concludeDrafts[sid]).toEqual({
          rating: 1,
          feedback: "notes",
          deleteWorktree: true,
          deleteBranch: false,
          analyzeLearnings: false,
        });
      });

      it("should keep conclude drafts isolated per session", () => {
        let state = uiReducer(initialState, setConcludeDraft({ sessionId: sid, rating: 5 }));
        state = uiReducer(state, setConcludeDraft({ sessionId: sid2, rating: 1 }));
        expect(state.concludeDrafts[sid].rating).toBe(5);
        expect(state.concludeDrafts[sid2].rating).toBe(1);
      });
    });

    it("clears the draft only on server-confirmed conclude (concludeSession)", () => {
      let state = uiReducer(initialState, setConcludeDraft({ sessionId: sid, rating: 4, feedback: "done" }));
      state = uiReducer(state, setConcludeDraft({ sessionId: sid2, rating: 2 }));
      state = uiReducer(state, concludeSession({ sessionId: sid, rating: 4, feedback: "done", concludedAt: "2024-01-01T00:00:00Z" }));
      expect(state.concludeDrafts[sid]).toBeUndefined();
      expect(state.concludeDrafts[sid2].rating).toBe(2);
    });

    describe("selectConcludeDraft", () => {
      it("should return the default draft for unknown or null session", () => {
        for (const sessionId of ["unknown", null]) {
          const draft = selectConcludeDraft({ ui: initialState }, sessionId);
          expect(draft).toEqual({ rating: 3, feedback: "", deleteWorktree: true, deleteBranch: true, analyzeLearnings: false });
        }
      });

      it("should return the existing draft", () => {
        const state = uiReducer(initialState, setConcludeDraft({ sessionId: sid, rating: 5 }));
        expect(selectConcludeDraft({ ui: state }, sid).rating).toBe(5);
      });
    });
  });
});

describe("setActiveSession", () => {
  it("switches left tab to git when a session becomes active", () => {
    const state = uiReducer({ ...initialState, leftTab: "help" }, setActiveSession("s-1"));
    expect(state.leftTab).toBe("git");
  });

  it("keeps the current tab when active session is cleared", () => {
    const state = uiReducer({ ...initialState, leftTab: "help" }, setActiveSession(null));
    expect(state.leftTab).toBe("help");
  });
});
