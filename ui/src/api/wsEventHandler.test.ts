import { describe, it, expect, vi } from "vitest";
import type { PayloadAction, UnknownAction } from "@reduxjs/toolkit";
import type { AppDispatch } from "@/store";
import { handleWsEvent } from "./wsEventHandler";
import type { WsEvent, GitStatusResponse, SessionStatus } from "@/types/api";

let mockStoreState: Record<string, unknown> = {
  sessions: { entities: {}, activeSessionId: null },
  projects: { entities: {}, ids: [] },
  workspace: { bySession: {}, diffMode: "all" },
};

vi.mock("@/store", () => ({
  store: { getState: () => mockStoreState },
}));

type Dispatched = UnknownAction | ((...args: never[]) => unknown);

function dispatchEvents(...events: WsEvent[]): Dispatched[] {
  const calls: Dispatched[] = [];
  const dispatch = (action: Dispatched) => {
    calls.push(action);
    return action;
  };
  for (const event of events) handleWsEvent(dispatch as unknown as AppDispatch, event);
  return calls;
}

const typeOf = (a: Dispatched) => (typeof a === "function" ? "thunk" : a.type);

const findAction = (calls: Dispatched[], type: string) =>
  calls.find((a) => typeOf(a) === type) as PayloadAction<Record<string, unknown>>;

const makeGitStatus = (overrides: Partial<GitStatusResponse> = {}): GitStatusResponse => ({
  session_id: "s1",
  branch: "main",
  ahead: 0,
  behind: 0,
  staged: [],
  unstaged: [{ path: "a.ts", status: "M", staged: false, additions: 3, deletions: 1 }],
  untracked: [],
  all_changes: [],
  ...overrides,
});

describe("wsEventHandler", () => {
  describe("cross-session streaming isolation", () => {
    it("should scope content_block_delta to the correct session", () => {
      const start = (session_id: string): WsEvent => ({
        type: "content_block_start",
        role: "assistant",
        session_id,
        content: [{ index: 0, type: "text" }],
      });
      const calls = dispatchEvents(start("s1"), start("s2"), {
        type: "content_block_delta",
        role: "assistant",
        session_id: "s1",
        content: [{ type: "text_delta", index: 0, text: "hello" }],
      });

      const deltaAction = findAction(calls, "messages/appendContentDelta");
      expect(deltaAction).toBeDefined();
      expect(deltaAction.payload.sessionId).toBe("s1");
    });

    it.each<[string, WsEvent, string]>([
      ["done", { type: "done", session_id: "s1" }, "s1"],
      [
        "assistant_message",
        { type: "assistant_message", role: "assistant", session_id: "s2", content: [{ type: "text", text: "hi" }] },
        "s2",
      ],
    ])("should scope clearStreamingContent to the session on %s", (_name, event, sessionId) => {
      const clearAction = findAction(dispatchEvents(event), "messages/clearStreamingContent");
      expect(clearAction).toBeDefined();
      expect(clearAction.payload).toBe(sessionId);
    });
  });

  describe("done event", () => {
    it("should clear streaming and pending approval", () => {
      const calls = dispatchEvents({ type: "done", session_id: "s1" });

      const types = calls.map(typeOf);
      expect(types).toContain("messages/clearStreamingContent");
      expect(types).toContain("messages/setSessionStreaming");
      expect(types).toContain("messages/clearAllPendingApprovals");
    });

    it.each([
      ["the sender is the active session", "s1"],
      ["another session is active", "s-active"],
    ])("dispatches upsertGitStatus keyed on the event's session when %s", (_name, activeSessionId) => {
      mockStoreState = {
        sessions: { entities: { s1: { id: "s1", project_id: "proj-1" } }, activeSessionId },
        projects: { entities: {}, ids: [] },
        workspace: { bySession: {}, diffMode: "all" },
      };
      const gitStatus = makeGitStatus();

      const calls = dispatchEvents({ type: "done", session_id: "s1", git_status: gitStatus } as WsEvent);

      const gitAction = findAction(calls, "workspace/upsertGitStatus");
      expect(gitAction).toBeDefined();
      expect(gitAction.payload).toEqual({ sessionId: "s1", status: gitStatus });
    });

    it("should dispatch loadSessionContext as the only thunk (file watcher handles loadFileTree)", () => {
      const calls = dispatchEvents({ type: "done", session_id: "s1" });

      const contextAction = calls.find(
        (a) => typeOf(a) === "thunk" || typeOf(a).startsWith("sessions/loadContext"),
      );
      expect(contextAction).toBeDefined();
      expect(calls.filter((a) => typeof a === "function")).toHaveLength(1);
    });

    it("also refetches the changes list when the session has a cached workspace", () => {
      const saved = mockStoreState;
      mockStoreState = { ...mockStoreState, workspace: { bySession: { s1: {} }, diffMode: "all" } };
      const calls = dispatchEvents({ type: "done", session_id: "s1" });
      expect(calls.filter((a) => typeof a === "function")).toHaveLength(2);
      mockStoreState = saved;
    });
  });

  describe("session_concluded auto-navigation", () => {
    const concluded = (session_id: string): WsEvent => ({
      type: "session_concluded",
      session_id,
      conclusion_rating: 4,
      conclusion_feedback: null,
      concluded_at: "2024-01-01T00:00:00Z",
    });

    const withSessions = (sessions: Array<Partial<import("@/types/api").Session> & { id: string }>, activeSessionId: string) => {
      const entities: Record<string, unknown> = {};
      for (const s of sessions) entities[s.id] = { status: "idle", parent_id: null, updated_at: "2024-01-01T00:00:00Z", ...s };
      mockStoreState = {
        sessions: { entities, ids: sessions.map((s) => s.id), activeSessionId },
        projects: { entities: {}, ids: [] },
      };
    };

    it("prefers an idle session over a busy one regardless of list order", () => {
      withSessions([
        { id: "s1" },
        { id: "busy-child", status: "tool_use", parent_id: "other-parent" },
        { id: "idle-1", status: "idle" },
      ], "s1");

      const action = findAction(dispatchEvents(concluded("s1")), "sessions/setActiveSession");
      expect(action.payload).toBe("idle-1");
    });

    it("prefers a busy top-level session over a busy dispatch child", () => {
      withSessions([
        { id: "s1" },
        { id: "busy-child", status: "tool_use", parent_id: "busy-parent" },
        { id: "busy-parent", status: "thinking" },
      ], "s1");

      const action = findAction(dispatchEvents(concluded("s1")), "sessions/setActiveSession");
      expect(action.payload).toBe("busy-parent");
    });

    it("never lands on the concluded session's own children", () => {
      withSessions([
        { id: "s1" },
        { id: "distill", status: "idle", parent_id: "s1" },
        { id: "other", status: "thinking" },
      ], "s1");

      const action = findAction(dispatchEvents(concluded("s1")), "sessions/setActiveSession");
      expect(action.payload).toBe("other");
    });

    it("does not navigate when the concluded session is not active", () => {
      withSessions([{ id: "s1" }, { id: "idle-1" }], "idle-1");

      expect(findAction(dispatchEvents(concluded("s1")), "sessions/setActiveSession")).toBeUndefined();
    });
  });

  describe("conclude_error event", () => {
    it("dispatches setConcludeError keyed by session so the error survives session switches", () => {
      const calls = dispatchEvents({
        type: "conclude_error",
        session_id: "s1",
        detail: "worktree has uncommitted changes",
      });

      const action = findAction(calls, "sessions/setConcludeError");
      expect(action).toBeDefined();
      expect(action.payload).toEqual({ sessionId: "s1", detail: "worktree has uncommitted changes" });
    });
  });

  describe("session_status_change event", () => {
    const statusChange = (status: SessionStatus): WsEvent => ({
      type: "session_status_change",
      session_id: "s1",
      content: [{ status }],
    });

    it("marks a session streaming so a turn this client never started is visible", () => {
      const calls = dispatchEvents(statusChange("thinking"));

      const action = findAction(calls, "messages/setSessionStreaming");
      expect(action.payload).toEqual({ sessionId: "s1", streaming: true });
      expect(findAction(calls, "sessions/updateSessionStatus")).toBeDefined();
    });

    it("clears streaming when the turn goes idle", () => {
      const calls = dispatchEvents(statusChange("idle"));

      expect(findAction(calls, "messages/setSessionStreaming").payload).toEqual({
        sessionId: "s1", streaming: false,
      });
    });

    it("leaves the streaming flag alone for statuses the terminal handlers own", () => {
      const calls = dispatchEvents(statusChange("error"), statusChange("concluded"));

      expect(findAction(calls, "messages/setSessionStreaming")).toBeUndefined();
    });
  });
});

describe("sandbox_status_change", () => {
  const event = (session_id: string): WsEvent => ({
    type: "sandbox_status_change",
    role: "system",
    session_id,
    content: [{ status: "running" }],
  });

  it("refetches workspace git state for cached sessions", () => {
    mockStoreState = {
      ...mockStoreState,
      workspace: { bySession: { s1: {} }, diffMode: "all" },
    };
    const calls = dispatchEvents(event("s1"));
    const types = calls.map(typeOf);
    expect(types.filter((t) => t === "thunk" || t.startsWith("workspace/")).length).toBe(3);
  });

  it("ignores sessions with no cached workspace", () => {
    mockStoreState = {
      ...mockStoreState,
      workspace: { bySession: {}, diffMode: "all" },
    };
    expect(dispatchEvents(event("s-unseen"))).toHaveLength(0);
  });
});
