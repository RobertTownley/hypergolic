import { describe, it, expect, vi, beforeEach } from "vitest";
import { configureStore, type UnknownAction } from "@reduxjs/toolkit";
import { reducers } from "@/store";
import { setActiveSession, upsertSession, addSession, removeSession } from "@/store/sessionsSlice";
import { focusListener } from "./focusListener";
import { dedupeTracker, resetDedupeTracking, resetDedupeKeyFns } from "./dedupeThunk";
import { makeSession } from "@/test/fixtures";
import * as gitApi from "@/api/git";
import * as filesApi from "@/api/files";
import * as sessionsApi from "@/api/sessions";

// Scoped responses carry session_id so workspaceSlice fulfilled handlers
// can route them to the right per-session slot. The value doesn't need
// to match any particular dispatched sessionId for these assertions
// (the tests only check the API was called); we just need the field to
// exist so the payload-keyed reducer path doesn't silently drop writes.
vi.mock("@/api/git", () => ({
  fetchGitStatus: vi.fn().mockResolvedValue({ session_id: "s", branch: "main", ahead: 0, behind: 0, staged: [], unstaged: [], untracked: [], all_changes: [] }),
  fetchGitBranches: vi.fn().mockResolvedValue({ session_id: "s", branches: ["main"], current: "main" }),
  fetchGitLog: vi.fn().mockResolvedValue({ session_id: "s", entries: [] }),
}));
vi.mock("@/api/files", () => ({
  fetchFileTree: vi.fn().mockResolvedValue({ session_id: "s", root: "/tmp", tree: [] }),
}));
vi.mock("@/api/projects", () => ({
  fetchProjects: vi.fn().mockResolvedValue([]),
}));
vi.mock("@/api/sessions", () => ({
  fetchSessions: vi.fn().mockResolvedValue([]),
  createSession: vi.fn(),
  deleteSession: vi.fn().mockResolvedValue(undefined),
}));

function makeStore() {
  return configureStore({
    reducer: reducers,
    middleware: (getDefault) => getDefault().prepend(focusListener.middleware).concat(dedupeTracker),
  });
}

type TestStore = ReturnType<typeof makeStore>;
type TestDispatch = TestStore["dispatch"];

/** Give the listener microtask a chance to flush. */
async function flushListener() {
  await Promise.resolve();
  await Promise.resolve();
}

function clearWorkspaceFetchMocks() {
  vi.mocked(gitApi.fetchGitStatus).mockClear();
  vi.mocked(gitApi.fetchGitBranches).mockClear();
  vi.mocked(gitApi.fetchGitLog).mockClear();
  vi.mocked(filesApi.fetchFileTree).mockClear();
}

function expectWorkspaceFanOut(sessionId: string) {
  expect(vi.mocked(gitApi.fetchGitStatus)).toHaveBeenCalledWith({ sessionId, repoScope: "app" }, "uncommitted");
  expect(vi.mocked(gitApi.fetchGitBranches)).toHaveBeenCalledWith({ sessionId });
  expect(vi.mocked(gitApi.fetchGitLog)).toHaveBeenCalledWith(50, { sessionId, repoScope: "app" });
  expect(vi.mocked(filesApi.fetchFileTree)).toHaveBeenCalledWith({ sessionId });
}

beforeEach(() => {
  resetDedupeTracking();
  resetDedupeKeyFns();
  clearWorkspaceFetchMocks();
});

describe("focusListener primary (setActiveSession)", () => {
  it("dispatches the four workspace loads on session change", async () => {
    const store = makeStore();
    store.dispatch(setActiveSession("s-b"));
    await flushListener();

    expectWorkspaceFanOut("s-b");
  });

  it("does not fire loadSessionContext (useChatView handles that)", async () => {
    const store = makeStore();
    const spy = vi.fn();
    // Patch loadSessionContext-shaped dispatches by wrapping dispatch.
    const origDispatch = store.dispatch;
    store.dispatch = ((action: unknown) => {
      const a = action as { type?: string };
      if (typeof a?.type === "string" && a.type.startsWith("sessions/loadContext")) {
        spy();
      }
      return origDispatch(action as UnknownAction);
    }) as TestDispatch;
    store.dispatch(setActiveSession("s-b"));
    await flushListener();
    expect(spy).not.toHaveBeenCalled();
  });

  it("is a no-op on null payload", async () => {
    const store = makeStore();
    store.dispatch(setActiveSession(null));
    await flushListener();
    expect(vi.mocked(gitApi.fetchGitStatus)).not.toHaveBeenCalled();
  });

  it("fires fan-out after addSession followed by explicit setActiveSession", async () => {
    // Regression: addSession.fulfilled used to set activeSessionId inline,
    // which caused focusListener's prev===next guard to short-circuit and
    // skip the workspace fan-out. It must no longer do that; callers
    // dispatch setActiveSession explicitly after addSession resolves.
    const store = makeStore();
    const newSession = makeSession({ id: "s-new", project_id: "proj-1" });
    vi.mocked(sessionsApi.createSession).mockResolvedValue(newSession);

    const result = await store.dispatch(
      addSession({ projectId: "proj-1", baseBranch: "main" }) as unknown as UnknownAction,
    );
    expect(addSession.fulfilled.match(result as UnknownAction)).toBe(true);
    // After the thunk resolves, activeSessionId must still be null — the
    // reducer no longer advances it inline.
    expect(store.getState().sessions.activeSessionId).toBe(null);

    store.dispatch(setActiveSession("s-new"));
    await flushListener();

    expectWorkspaceFanOut("s-new");
  });

  it("is a no-op when the id hasn't changed", async () => {
    const store = makeStore();
    // First dispatch populates originalState.activeSessionId -> sessionId.
    store.dispatch(setActiveSession("s-a"));
    await flushListener();
    vi.mocked(gitApi.fetchGitStatus).mockClear();
    // Same id — should not re-fan-out.
    store.dispatch(setActiveSession("s-a"));
    await flushListener();
    expect(vi.mocked(gitApi.fetchGitStatus)).not.toHaveBeenCalled();
  });
});

describe("focusListener tertiary (removeSession)", () => {
  it("advances to the next surviving session when the active one is removed", async () => {
    const store = makeStore();
    store.dispatch(upsertSession(makeSession({ id: "s-1", project_id: "proj-1" })));
    store.dispatch(upsertSession(makeSession({ id: "s-2", project_id: "proj-1" })));
    store.dispatch(setActiveSession("s-1"));
    await flushListener();
    clearWorkspaceFetchMocks();

    await store.dispatch(removeSession("s-1") as unknown as UnknownAction);
    // Allow the listener microtask + the setActiveSession effect to flush.
    await flushListener();

    expect(store.getState().sessions.activeSessionId).toBe("s-2");
    // Workspace mirror must match so panels render the new slot.
    expect(store.getState().workspace.activeSessionId).toBe("s-2");
    // Primary listener should have fanned out loads for s-2.
    expectWorkspaceFanOut("s-2");
  });

  it("leaves activeSessionId null when the last session is removed", async () => {
    const store = makeStore();
    store.dispatch(upsertSession(makeSession({ id: "s-1", project_id: "proj-1" })));
    store.dispatch(setActiveSession("s-1"));
    await flushListener();

    await store.dispatch(removeSession("s-1") as unknown as UnknownAction);
    await flushListener();

    expect(store.getState().sessions.activeSessionId).toBe(null);
    expect(store.getState().workspace.activeSessionId).toBe(null);
  });

  it("is a no-op when a background (non-active) session is removed", async () => {
    const store = makeStore();
    store.dispatch(upsertSession(makeSession({ id: "s-active", project_id: "proj-1" })));
    store.dispatch(upsertSession(makeSession({ id: "s-bg", project_id: "proj-1" })));
    store.dispatch(setActiveSession("s-active"));
    await flushListener();
    clearWorkspaceFetchMocks();

    await store.dispatch(removeSession("s-bg") as unknown as UnknownAction);
    await flushListener();

    // Active session unchanged; no new fan-out.
    expect(store.getState().sessions.activeSessionId).toBe("s-active");
    expect(store.getState().workspace.activeSessionId).toBe("s-active");
    expect(vi.mocked(gitApi.fetchGitStatus)).not.toHaveBeenCalled();
  });
});
