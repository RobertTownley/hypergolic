import { describe, it, expect } from "vitest";
import sessionsReducer, { setActiveSession, updateSessionStatus, updateSessionWorkflow, upsertSession, updateSessionDescription, concludeSession, setConcludeError, clearConcludeError, selectConcludeError, loadSessionContext, addSession } from "./sessionsSlice";
import { makeSession } from "@/test/fixtures";
import type { Session, SessionContext } from "@/types/api";

const initialState = {
  entities: {} as Record<string, Session>,
  ids: [] as string[],
  activeSessionId: null as string | null,
  initialized: false,
  loading: false,
  error: null as string | null,
  contextBySessionId: {} as Record<string, SessionContext>,
  concludeErrorBySessionId: {} as Record<string, string | null>,
};

type SessionsState = typeof initialState;

function stateWith(sessions: Session[], extra: Partial<SessionsState> = {}): SessionsState {
  return {
    ...initialState,
    entities: Object.fromEntries(sessions.map((s) => [s.id, s])),
    ids: sessions.map((s) => s.id),
    ...extra,
  };
}

const removeFulfilled = (id: string) => ({ type: "sessions/remove/fulfilled", payload: id });

const sampleContext = {
  tools: [],
  tools_count: 10,
  tools_token_estimate: 200,
  skills_summary: { total: 3, activated: [] },
  mcp_enabled: [],
  prompt_token_estimate: 500,
};

describe("sessionsSlice", () => {
  it("should return the initial state", () => {
    expect(sessionsReducer(undefined, { type: "unknown" })).toEqual(initialState);
  });

  it("should update session status", () => {
    const state = sessionsReducer(stateWith([makeSession({ id: "s1" })]), updateSessionStatus({ sessionId: "s1", status: "streaming" }));
    expect(state.entities["s1"].status).toBe("streaming");
  });

  it("should update session workflow state", () => {
    const state = sessionsReducer(
      stateWith([makeSession({ id: "s1" })]),
      updateSessionWorkflow({
        sessionId: "s1",
        workflowId: "feature-dev",
        workflowName: "Feature Development",
        workflowStateId: "planning",
        workflowStateName: "Planning",
      }),
    );
    expect(state.entities["s1"].workflow_id).toBe("feature-dev");
    expect(state.entities["s1"].workflow_name).toBe("Feature Development");
    expect(state.entities["s1"].workflow_state_id).toBe("planning");
    expect(state.entities["s1"].workflow_state_name).toBe("Planning");
  });

  it("should clear workflow state when set to null", () => {
    const prior = stateWith([
      makeSession({ id: "s1", workflow_id: "feature-dev", workflow_state_id: "planning", workflow_state_name: "Planning" }),
    ]);
    const state = sessionsReducer(
      prior,
      updateSessionWorkflow({ sessionId: "s1", workflowId: null, workflowName: null, workflowStateId: null, workflowStateName: null }),
    );
    expect(state.entities["s1"].workflow_id).toBeNull();
    expect(state.entities["s1"].workflow_name).toBeNull();
    expect(state.entities["s1"].workflow_state_id).toBeNull();
    expect(state.entities["s1"].workflow_state_name).toBeNull();
  });

  it.each([
    ["status", updateSessionStatus({ sessionId: "unknown", status: "error" })],
    ["description", updateSessionDescription({ sessionId: "unknown", description: "test" })],
  ])("should ignore %s update for unknown session", (_field, action) => {
    const state = sessionsReducer(initialState, action);
    expect(state.entities["unknown"]).toBeUndefined();
  });

  it("should clean up entities, context, and conclude error on session removal", () => {
    const prior = stateWith([makeSession({ id: "s1" })], {
      activeSessionId: "s1",
      contextBySessionId: { s1: sampleContext },
      concludeErrorBySessionId: { s1: "worktree dirty" },
    });
    const state = sessionsReducer(prior, removeFulfilled("s1"));
    expect(state.contextBySessionId["s1"]).toBeUndefined();
    expect(state.concludeErrorBySessionId["s1"]).toBeUndefined();
    expect(state.ids).not.toContain("s1");
  });

  it("nulls activeSessionId (no inline advance) when the active session is removed", () => {
    // Inline advancing here would leave workspaceSlice.activeSessionId
    // pointing at the deleted id while sessionsSlice jumped ahead.
    // focusListener dispatches setActiveSession(next) after the reducer
    // so both slices stay in sync; that advance is tested in
    // focusListener.test.ts.
    const prior = stateWith([makeSession({ id: "s1" }), makeSession({ id: "s2" })], { activeSessionId: "s1" });
    const state = sessionsReducer(prior, removeFulfilled("s1"));
    expect(state.activeSessionId).toBeNull();
    expect(state.ids).toEqual(["s2"]);
  });

  it("leaves activeSessionId alone when a background session is removed", () => {
    const prior = stateWith([makeSession({ id: "s1" }), makeSession({ id: "s2" })], { activeSessionId: "s1" });
    const state = sessionsReducer(prior, removeFulfilled("s2"));
    expect(state.activeSessionId).toBe("s1");
  });

  describe("session ordering", () => {
    const baseState = stateWith([
      makeSession({ id: "s1", status: "idle", updated_at: "2024-01-01T00:00:00Z" }),
      makeSession({ id: "s2", status: "idle", updated_at: "2024-01-03T00:00:00Z" }),
      makeSession({ id: "s3", status: "awaiting_approval", updated_at: "2024-01-02T00:00:00Z" }),
      makeSession({ id: "s4", status: "streaming", updated_at: "2024-01-01T12:00:00Z" }),
    ]);

    it("should sort active session first", () => {
      const state = sessionsReducer(baseState, setActiveSession("s1"));
      expect(state.ids[0]).toBe("s1");
    });

    it.each([
      // active > awaiting_approval > streaming > idle
      ["s2", ["s2", "s3", "s4", "s1"]],
      ["s1", ["s1", "s3", "s4", "s2"]],
    ])("should sort action-required before busy before idle (active %s)", (active, expected) => {
      const state = sessionsReducer(baseState, setActiveSession(active));
      expect(state.ids).toEqual(expected);
    });

    it("should sort by updated_at within the same tier", () => {
      const twoIdleState = stateWith([
        makeSession({ id: "a", status: "idle", updated_at: "2024-01-01T00:00:00Z" }),
        makeSession({ id: "b", status: "idle", updated_at: "2024-01-05T00:00:00Z" }),
      ]);
      const state = sessionsReducer(twoIdleState, setActiveSession(null));
      expect(state.ids).toEqual(["b", "a"]);
    });

    it("should re-sort on status change promoting a session", () => {
      const state = sessionsReducer(
        { ...baseState, activeSessionId: "s2" },
        updateSessionStatus({ sessionId: "s1", status: "error" }),
      );
      // s2 active, s1+s3 action-required (s1 newer updated_at from the status change), s4 busy
      expect(state.ids[0]).toBe("s2");
      expect(state.ids.indexOf("s1")).toBeLessThan(state.ids.indexOf("s4"));
      expect(state.ids.indexOf("s3")).toBeLessThan(state.ids.indexOf("s4"));
    });
  });

  it("updateSessionDescription updates an existing session", () => {
    const state = sessionsReducer(stateWith([makeSession({ id: "s1" })]), updateSessionDescription({ sessionId: "s1", description: "My session" }));
    expect(state.entities["s1"].description).toBe("My session");
  });

  describe("upsertSession", () => {
    it("should add a new session", () => {
      const session = makeSession({ id: "new-1", status: "idle" });
      const state = sessionsReducer(initialState, upsertSession(session));
      expect(state.entities["new-1"]).toEqual(session);
      expect(state.ids).toContain("new-1");
    });

    it("should update an existing session without duplicating ids", () => {
      const prior = stateWith([makeSession({ id: "s1", status: "idle" })]);
      const state = sessionsReducer(prior, upsertSession(makeSession({ id: "s1", status: "streaming" })));
      expect(state.entities["s1"].status).toBe("streaming");
      expect(state.ids.filter((id) => id === "s1")).toHaveLength(1);
    });
  });

  describe("addSession.fulfilled", () => {
    it("inserts the new session but does NOT set it active", () => {
      // Callers must dispatch setActiveSession explicitly so focusListener
      // observes a real prev->next transition. If this reducer set
      // activeSessionId inline, the listener's originalState guard would
      // short-circuit and the workspace panels would never refresh.
      const session = makeSession({ id: "new-1" });
      const state = sessionsReducer(initialState, { type: addSession.fulfilled.type, payload: session });
      expect(state.entities["new-1"]).toEqual(session);
      expect(state.ids).toContain("new-1");
      expect(state.activeSessionId).toBeNull();
    });

    it("preserves any existing active session", () => {
      const prior = stateWith([makeSession({ id: "s0" })], { activeSessionId: "s0" });
      const state = sessionsReducer(prior, { type: addSession.fulfilled.type, payload: makeSession({ id: "new-1" }) });
      expect(state.activeSessionId).toBe("s0");
      expect(state.ids).toEqual(["new-1", "s0"]);
    });
  });

  describe("conclude errors", () => {
    it("clearConcludeError removes only that session's error", () => {
      let state = sessionsReducer(initialState, setConcludeError({ sessionId: "s1", detail: "worktree dirty" }));
      state = sessionsReducer(state, setConcludeError({ sessionId: "s2", detail: "other" }));
      state = sessionsReducer(state, clearConcludeError("s1"));
      expect(state.concludeErrorBySessionId).toEqual({ s2: "other" });
    });

    it("concludeSession clears any pending error for that session", () => {
      let state = sessionsReducer(stateWith([makeSession({ id: "s1" })]), setConcludeError({ sessionId: "s1", detail: "worktree dirty" }));
      state = sessionsReducer(state, concludeSession({ sessionId: "s1", rating: 4, feedback: null, concludedAt: "2024-01-01T00:00:00Z" }));
      expect(state.concludeErrorBySessionId["s1"]).toBeUndefined();
      expect(state.entities["s1"].conclusion_rating).toBe(4);
    });

    it("selectConcludeError returns the detail, or null for unknown or null session", () => {
      const state = sessionsReducer(initialState, setConcludeError({ sessionId: "s1", detail: "worktree dirty" }));
      expect(selectConcludeError({ sessions: state }, "s1")).toBe("worktree dirty");
      expect(selectConcludeError({ sessions: state }, "unknown")).toBeNull();
      expect(selectConcludeError({ sessions: state }, null)).toBeNull();
    });
  });

  it("should store context on loadSessionContext.fulfilled", () => {
    const context = {
      ...sampleContext,
      tools_count: 42,
      skills_summary: { total: 5, activated: [] },
      mcp_enabled: ["server-a"],
    };
    const state = sessionsReducer(initialState, {
      type: loadSessionContext.fulfilled.type,
      payload: { sessionId: "s1", context },
    });
    expect(state.contextBySessionId["s1"]).toEqual(context);
  });
});
