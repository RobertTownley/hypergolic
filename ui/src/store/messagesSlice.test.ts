import { describe, it, expect } from "vitest";
import messagesReducer, {
  loadMessages,
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
  type PendingApproval,
} from "./messagesSlice";
import { removeSession } from "./sessionsSlice";
import type { Message } from "@/types/api";

const initialState = {
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

type MessagesState = ReturnType<typeof messagesReducer>;

function makeStoredMessage(id: string, sessionId: string): Message {
  return { id, session_id: sessionId, role: "user", content: [{ type: "text", text: "hi" }], created_at: new Date().toISOString() };
}

function makeApproval(toolUseId: string, toolName = "cmd", sessionId = "s1"): PendingApproval {
  return { toolUseId, toolName, toolId: toolName, toolInput: {}, sessionId };
}

const loadPending = (sessionId: string) => ({
  type: loadMessages.pending.type,
  meta: { arg: sessionId, requestId: "req1", requestStatus: "pending" as const },
});
const loadFulfilled = (sessionId: string, messages: Message[], fetchedAt = new Date().toISOString()) => ({
  type: loadMessages.fulfilled.type,
  payload: { sessionId, messages, fetchedAt },
  meta: { arg: sessionId, requestId: "req1", requestStatus: "fulfilled" as const },
});

/** startContentBlock(text) at index 0 for the given session. */
const startText = (sessionId: string) => startContentBlock({ sessionId, index: 0, blockType: "text" });

describe("messagesSlice", () => {
  it("should return the initial state", () => {
    expect(messagesReducer(undefined, { type: "unknown" })).toEqual(initialState);
  });


  it("should track per-session streaming", () => {
    let state = messagesReducer(initialState, setSessionStreaming({ sessionId: "s1", streaming: true }));
    expect(state.streamingSessions["s1"]).toBe(true);
    expect(state.streaming).toBe(true);

    state = messagesReducer(state, setSessionStreaming({ sessionId: "s2", streaming: true }));
    expect(state.streamingSessions["s2"]).toBe(true);
    expect(state.streaming).toBe(true);

    state = messagesReducer(state, setSessionStreaming({ sessionId: "s1", streaming: false }));
    expect(state.streamingSessions["s1"]).toBeUndefined();
    expect(state.streaming).toBe(true);

    state = messagesReducer(state, setSessionStreaming({ sessionId: "s2", streaming: false }));
    expect(state.streamingSessions["s2"]).toBeUndefined();
    expect(state.streaming).toBe(false);
  });

  it("should clear transient error on loadMessages fulfilled", () => {
    let state = messagesReducer(initialState, setSessionError({ sessionId: "s1", error: "some error" }));
    expect(state.errorBySessionId["s1"]).toBe("some error");

    state = messagesReducer(state, loadFulfilled("s1", []));
    expect(state.errorBySessionId["s1"]).toBeUndefined();
  });

  it("should keep optimistic user messages newer than the fetch on reload", () => {
    const fetchedAt = new Date(Date.now() - 1000).toISOString();
    const state0 = messagesReducer(initialState, addUserMessage({ sessionId: "s1", text: "racing send" }));
    const state = messagesReducer(state0, loadFulfilled("s1", [], fetchedAt));
    expect(state.bySessionId["s1"]).toHaveLength(1);
    expect(state.bySessionId["s1"][0].content.at(-1)?.text).toBe("racing send");
  });

  it("should drop optimistic user messages the fetch already covered", () => {
    const state0 = messagesReducer(initialState, addUserMessage({ sessionId: "s1", text: "old send" }));
    const fetchedAt = new Date(Date.now() + 1000).toISOString();
    const state = messagesReducer(state0, loadFulfilled("s1", [], fetchedAt));
    expect(state.bySessionId["s1"]).toHaveLength(0);
  });

  it("should add a user message", () => {
    const state = messagesReducer(initialState, addUserMessage({ sessionId: "s1", text: "hello" }));
    expect(state.bySessionId["s1"]).toHaveLength(1);
    expect(state.bySessionId["s1"][0].role).toBe("user");
    expect(state.bySessionId["s1"][0].content[0].text).toBe("hello");
  });

  it("should add a user message with content blocks", () => {
    const imageBlock = {
      type: "image",
      source: { type: "base64" as const, media_type: "image/png", data: "abc123" },
    };
    const state = messagesReducer(
      initialState,
      addUserMessage({ sessionId: "s1", text: "look at this", contentBlocks: [imageBlock] })
    );
    expect(state.bySessionId["s1"]).toHaveLength(1);
    const msg = state.bySessionId["s1"][0];
    expect(msg.content).toHaveLength(2);
    expect(msg.content[0].type).toBe("image");
    expect(msg.content[0].source).toEqual(imageBlock.source);
    expect(msg.content[1].type).toBe("text");
    expect(msg.content[1].text).toBe("look at this");
  });

  it("should add an assistant message", () => {
    const state = messagesReducer(
      initialState,
      addAssistantMessage({ sessionId: "s1", content: [{ type: "text", text: "greetings" }], model: "claude-3" })
    );
    expect(state.bySessionId["s1"]).toHaveLength(1);
    expect(state.bySessionId["s1"][0].role).toBe("assistant");
    expect(state.bySessionId["s1"][0].model).toBe("claude-3");
  });

  it("should add a tool result", () => {
    const state = messagesReducer(
      initialState,
      addToolResult({
        sessionId: "s1",
        content: [{ type: "tool_result", tool_use_id: "t1", content: [{ type: "text", text: "output" }] }],
      })
    );
    expect(state.bySessionId["s1"]).toHaveLength(1);
    expect(state.bySessionId["s1"][0].content[0].type).toBe("tool_result");
  });

  it("should track loading state for messages", () => {
    let state = messagesReducer(initialState, loadPending("s1"));
    expect(state.loadingSessionIds["s1"]).toBe(true);

    state = messagesReducer(state, loadFulfilled("s1", [makeStoredMessage("m1", "s1")]));
    expect(state.loadingSessionIds["s1"]).toBeUndefined();
    expect(state.bySessionId["s1"]).toHaveLength(1);
  });

  it("should clear loading state on rejection", () => {
    let state = messagesReducer(initialState, loadPending("s1"));
    expect(state.loadingSessionIds["s1"]).toBe(true);

    state = messagesReducer(state, {
      type: loadMessages.rejected.type,
      error: { message: "Network error" },
      meta: { arg: "s1", requestId: "req1", requestStatus: "rejected" as const, aborted: false, condition: false },
    });
    expect(state.loadingSessionIds["s1"]).toBeUndefined();
  });

  it("should clean up messages when a session is removed", () => {
    const stateWithData = {
      ...initialState,
      bySessionId: { s1: [makeStoredMessage("1", "s1")], s2: [makeStoredMessage("2", "s2")] },
      errorBySessionId: { s1: "some error" },
      pendingApprovalBySession: { s1: [makeApproval("t1")] },
    };
    const state = messagesReducer(stateWithData, { type: removeSession.fulfilled.type, payload: "s1" });
    expect(state.bySessionId["s1"]).toBeUndefined();
    expect(state.errorBySessionId["s1"]).toBeUndefined();
    expect(state.pendingApprovalBySession["s1"]).toBeUndefined();
    expect(state.bySessionId["s2"]).toBeDefined();
  });

  it("should start a content block", () => {
    const state = messagesReducer(initialState, startText("s1"));
    expect(state.streamingBlocksBySessionId["s1"][0]).toEqual({ type: "text", text: "", id: undefined, name: undefined, display_name: undefined, partialJson: undefined });
  });

  it("should start a tool_call content block", () => {
    const state = messagesReducer(
      initialState,
      startContentBlock({ sessionId: "s1", index: 0, blockType: "tool_call", id: "tu_1", name: "cat", display_name: "Read Files" })
    );
    expect(state.streamingBlocksBySessionId["s1"][0]).toEqual({ type: "tool_call", text: undefined, id: "tu_1", name: "cat", display_name: "Read Files", partialJson: "" });
  });

  it("should append text delta", () => {
    let state = messagesReducer(initialState, startText("s1"));
    state = messagesReducer(state, appendContentDelta({ sessionId: "s1", index: 0, text: "Hello" }));
    state = messagesReducer(state, appendContentDelta({ sessionId: "s1", index: 0, text: " world" }));
    expect(state.streamingBlocksBySessionId["s1"][0].text).toBe("Hello world");
  });

  it("should clear streaming content for a specific session", () => {
    let state = messagesReducer(initialState, startText("s1"));
    state = messagesReducer(state, appendContentDelta({ sessionId: "s1", index: 0, text: "Hello" }));
    state = messagesReducer(state, clearStreamingContent("s1"));
    expect(state.streamingBlocksBySessionId["s1"]).toBeUndefined();
  });

  describe("pending approval queue", () => {
    const approval1 = makeApproval("t1", "cmd1");
    const approval2 = makeApproval("t2", "cmd2");

    function stateWithTwoApprovals(): MessagesState {
      const state = messagesReducer(initialState, setPendingApproval(approval1));
      return messagesReducer(state, setPendingApproval(approval2));
    }

    it("should queue multiple pending approvals for same session", () => {
      const state = stateWithTwoApprovals();
      expect(state.pendingApprovalBySession["s1"]).toHaveLength(2);
      expect(state.pendingApprovalBySession["s1"][0].toolUseId).toBe("t1");
      expect(state.pendingApprovalBySession["s1"][1].toolUseId).toBe("t2");
    });

    it("should clear specific pending approval by toolUseId", () => {
      const state = messagesReducer(stateWithTwoApprovals(), clearPendingApproval({ sessionId: "s1", toolUseId: "t1" }));
      expect(state.pendingApprovalBySession["s1"]).toHaveLength(1);
      expect(state.pendingApprovalBySession["s1"][0].toolUseId).toBe("t2");
    });

    it("should delete session key when last approval is cleared", () => {
      let state = messagesReducer(initialState, setPendingApproval(approval1));
      state = messagesReducer(state, clearPendingApproval({ sessionId: "s1", toolUseId: "t1" }));
      expect(state.pendingApprovalBySession["s1"]).toBeUndefined();
    });

    it("should clear all pending approvals for a session", () => {
      const state = messagesReducer(stateWithTwoApprovals(), clearAllPendingApprovals("s1"));
      expect(state.pendingApprovalBySession["s1"]).toBeUndefined();
    });
  });

  describe("per-session streaming isolation", () => {
    /** Two sessions, each with an open text block at index 0. */
    function stateWithTwoStreams(): MessagesState {
      const state = messagesReducer(initialState, startText("s1"));
      return messagesReducer(state, startText("s2"));
    }

    it("should scope appendContentDelta to the correct session and keep blocks independent", () => {
      let state = messagesReducer(stateWithTwoStreams(), appendContentDelta({ sessionId: "s1", index: 0, text: "only s1" }));
      expect(state.streamingBlocksBySessionId["s1"][0].text).toBe("only s1");
      expect(state.streamingBlocksBySessionId["s2"][0].text).toBe("");

      state = messagesReducer(state, appendContentDelta({ sessionId: "s2", index: 0, text: "Session 2" }));
      expect(state.streamingBlocksBySessionId["s1"][0].text).toBe("only s1");
      expect(state.streamingBlocksBySessionId["s2"][0].text).toBe("Session 2");
    });

    it("should not affect other sessions when clearing streaming content", () => {
      let state = messagesReducer(stateWithTwoStreams(), appendContentDelta({ sessionId: "s1", index: 0, text: "Hello" }));
      state = messagesReducer(state, appendContentDelta({ sessionId: "s2", index: 0, text: "World" }));

      state = messagesReducer(state, clearStreamingContent("s1"));

      expect(state.streamingBlocksBySessionId["s1"]).toBeUndefined();
      expect(state.streamingBlocksBySessionId["s2"][0].text).toBe("World");
    });

    it("should clean up streaming blocks when a session is removed", () => {
      let state = messagesReducer(initialState, startText("s1"));
      state = messagesReducer(state, appendContentDelta({ sessionId: "s1", index: 0, text: "Hello" }));

      state = messagesReducer(state, { type: removeSession.fulfilled.type, payload: "s1" });

      expect(state.streamingBlocksBySessionId["s1"]).toBeUndefined();
    });
  });
});

describe("live tool output", () => {
  it("appends chunks and keeps only a display-sized tail", () => {
    let state = messagesReducer(initialState, appendToolOutput({ toolUseId: "t1", text: "a".repeat(3999) }));
    state = messagesReducer(state, appendToolOutput({ toolUseId: "t1", text: "bb" }));
    expect(state.liveToolOutputByToolUseId["t1"]).toHaveLength(4000);
    expect(state.liveToolOutputByToolUseId["t1"].endsWith("bb")).toBe(true);
  });

  it("drops the live tail when the call's result lands", () => {
    let state = messagesReducer(initialState, appendToolOutput({ toolUseId: "t1", text: "out" }));
    state = messagesReducer(state, addToolResult({
      sessionId: "s1",
      content: [{ type: "tool_result", tool_use_id: "t1", content: [] }],
    }));
    expect(state.liveToolOutputByToolUseId["t1"]).toBeUndefined();
  });
});
