import { describe, it, expect } from "vitest";
import type { UnknownAction } from "@reduxjs/toolkit";
import workspaceReducer, {
  setDiffMode,
  clearDiff,
  clearActionOutput,
  clearError,
  upsertGitStatus,
  selectFile,
  setSandboxContainer,
  setSandboxRoot,
  selectSandboxFile,
  refreshSandbox,
} from "./workspaceSlice";
import {
  loadGitStatus,
  loadBranches,
  loadDiff,
  loadFileTree,
  loadFileContent,
  loadSandboxContainers,
  loadSandboxDir,
  loadSandboxContent,
} from "./workspaceThunks";
import {
  emptySessionWorkspace,
  WORKSPACE_LRU_CAP,
  type SessionWorkspace,
  type FileSource,
} from "./workspace/state";
import { setActiveSession, removeSession } from "./sessionsSlice";
import { SANDBOX_STARTING } from "@/api/files";
import type { GitStatusResponse, DiffMode } from "@/types/api";

interface TestState {
  bySession: Record<string, SessionWorkspace>;
  lruOrder: string[];
  activeSessionId: string | null;
  actionLoading: boolean;
  actionOutput: string | null;
  error: string | null;
  diffMode: DiffMode;
  repoScope: "app" | "harness" | "shared";
  fileSource: FileSource;
}

const initialState: TestState = {
  bySession: {},
  lruOrder: [],
  activeSessionId: null,
  actionLoading: false,
  actionOutput: null,
  error: null,
  diffMode: "all",
  repoScope: "app",
  fileSource: "host",
};

/** Build a `thunk.fulfilled` action; arg defaults to the "s1" session most tests seed. */
function fulfilled(thunk: { fulfilled: { type: string } }, payload: unknown, arg: unknown = { sessionId: "s1" }): UnknownAction {
  // Repo-scoped thunks stamp payloads with the repoScope they fetched for.
  const scoped = /loadGitStatus|loadGitLog|loadChanges|loadCommitDetail|loadDiff/.test(thunk.fulfilled.type);
  const stamped = scoped && typeof payload === "object" && payload !== null
    ? { repoScope: "app" as const, ...payload }
    : payload;
  return { type: thunk.fulfilled.type, payload: stamped, meta: { arg } };
}

function rejected(thunk: { rejected: { type: string } }, message: string, arg: unknown = { sessionId: "s1" }): UnknownAction {
  return { type: thunk.rejected.type, error: { message }, meta: { arg } };
}

// session_id defaults to "s1" to match the session id most tests seed;
// callers that interleave sessions (e.g. sA/sB tests) pass an explicit
// override. Keeping the field on every response mirrors what the backend
// now guarantees and lets payload-keyed fulfilled reducers land writes.
function makeStatus(overrides: Partial<GitStatusResponse> = {}): GitStatusResponse {
  return {
    session_id: "s1",
    branch: "main",
    ahead: 0,
    behind: 0,
    staged: [],
    unstaged: [],
    untracked: [],
    all_changes: [],
    ...overrides,
  };
}

/** Shorthand for a state with one active session whose slot is present. */
function stateWithActiveSession(sessionId: string, slotOverrides: Partial<SessionWorkspace> = {}): TestState {
  return {
    ...initialState,
    bySession: { [sessionId]: { ...emptySessionWorkspace(), ...slotOverrides } },
    lruOrder: [sessionId],
    activeSessionId: sessionId,
  };
}

describe("workspaceSlice", () => {
  it("returns the initial state", () => {
    expect(workspaceReducer(undefined, { type: "unknown" })).toEqual(initialState);
  });

  describe("top-level reducers", () => {
    it("clearActionOutput", () => {
      const state = workspaceReducer({ ...initialState, actionOutput: "pushed" }, clearActionOutput());
      expect(state.actionOutput).toBeNull();
    });

    it("setDiffMode updates mode and clears the active slot's selectedDiff", () => {
      const prior = stateWithActiveSession("s1", {
        selectedDiff: { session_id: "s1", path: "a.ts", diff: "+x" },
      });
      const state = workspaceReducer(prior, setDiffMode("uncommitted"));
      expect(state.diffMode).toBe("uncommitted");
      expect(state.bySession["s1"].selectedDiff).toBeNull();
    });

    it("clearError clears both top-level and active-slot statusError", () => {
      const prior: TestState = { ...stateWithActiveSession("s1", { statusError: "prev" }), error: "top-level" };
      const state = workspaceReducer(prior, clearError());
      expect(state.error).toBeNull();
      expect(state.bySession["s1"].statusError).toBeNull();
    });
  });

  describe("setActiveSession", () => {
    it("mirrors activeSessionId and hydrates an empty slot with loading=true", () => {
      const state = workspaceReducer(initialState, setActiveSession("s1"));
      const slot = state.bySession["s1"];
      expect(state.activeSessionId).toBe("s1");
      expect(slot).toBeDefined();
      expect(slot.loading).toBe(true);
      expect(slot.branchesLoading).toBe(true);
      expect(slot.treeLoading).toBe(true);
      expect(slot.logLoading).toBe(true);
      // User-triggered loads stay false.
      expect(slot.diffLoading).toBe(false);
      expect(slot.commitDetailLoading).toBe(false);
      expect(slot.fileContentLoading).toBe(false);
      expect(state.lruOrder).toEqual(["s1"]);
    });

    it("preserves the previous session's slot when switching to a new one", () => {
      let state = workspaceReducer(initialState, setActiveSession("s1"));
      state = workspaceReducer(state, fulfilled(loadGitStatus, makeStatus({ branch: "sA" })));
      state = workspaceReducer(state, setActiveSession("s2"));
      expect(state.bySession["s1"].status?.branch).toBe("sA");
      expect(state.bySession["s2"]).toBeDefined();
      expect(state.bySession["s2"].status).toBeNull();
    });

    it("returning to a session keeps its cached data (round-trip)", () => {
      let state = workspaceReducer(initialState, setActiveSession("s1"));
      state = workspaceReducer(state, fulfilled(loadFileTree, {
        session_id: "s1",
        root: "/a",
        tree: [{ name: "a.ts", path: "a.ts", is_dir: false, git_status: null, children: [] }],
      }));
      state = workspaceReducer(state, setActiveSession("s2"));
      state = workspaceReducer(state, setActiveSession("s1"));
      expect(state.bySession["s1"].root).toBe("/a");
      expect(state.bySession["s1"].tree).toHaveLength(1);
      // Returning to s1 re-sets its loading booleans to true for another fan-out.
      expect(state.bySession["s1"].loading).toBe(true);
    });

    it("null payload clears active mirror and top-level ephemera", () => {
      const prior = { ...stateWithActiveSession("s1"), actionOutput: "pushed", error: "stale" };
      const state = workspaceReducer(prior, setActiveSession(null));
      expect(state.activeSessionId).toBeNull();
      expect(state.actionOutput).toBeNull();
      expect(state.error).toBeNull();
      // Previous slot is untouched.
      expect(state.bySession["s1"]).toBeDefined();
    });
  });

  describe("per-session writes", () => {
    const treePayload = {
      session_id: "s1",
      root: "/project",
      tree: [{ name: "src", path: "src", is_dir: true, git_status: null, children: [] }],
    };
    const contentPayload = { session_id: "s1", path: "main.py", content: "print('hi')", language: "python" };
    const diffPayload = { session_id: "s1", path: "a.ts", diff: "+x" };

    it.each<{ name: string; action: UnknownAction; assert: (slot: SessionWorkspace) => void }>([
      {
        name: "loadGitStatus.fulfilled writes status",
        action: fulfilled(loadGitStatus, makeStatus({ branch: "feature" })),
        assert: (slot) => {
          expect(slot.status?.branch).toBe("feature");
          expect(slot.loading).toBe(false);
        },
      },
      {
        name: "loadGitStatus.rejected writes statusError",
        action: rejected(loadGitStatus, "boom"),
        assert: (slot) => {
          expect(slot.statusError).toBe("boom");
          expect(slot.loading).toBe(false);
        },
      },
      {
        name: "loadBranches.fulfilled populates branches",
        action: fulfilled(loadBranches, { session_id: "s1", branches: ["main", "dev"], current: "main" }),
        assert: (slot) => {
          expect(slot.branches).toEqual(["main", "dev"]);
          expect(slot.branchesLoading).toBe(false);
        },
      },
      {
        name: "loadFileTree.fulfilled stores root+tree",
        action: fulfilled(loadFileTree, treePayload),
        assert: (slot) => {
          expect(slot.root).toBe("/project");
          expect(slot.tree).toEqual(treePayload.tree);
          expect(slot.treeLoading).toBe(false);
        },
      },
      {
        name: "loadFileContent.fulfilled stores content",
        action: fulfilled(loadFileContent, contentPayload, { sessionId: "s1", path: "main.py" }),
        assert: (slot) => {
          expect(slot.fileContent).toEqual(contentPayload);
          expect(slot.fileContentLoading).toBe(false);
        },
      },
      {
        name: "loadDiff.fulfilled stores selectedDiff",
        action: fulfilled(loadDiff, diffPayload, { sessionId: "s1", path: "a.ts", staged: false }),
        assert: (slot) => {
          expect(slot.selectedDiff).toEqual({ repoScope: "app", ...diffPayload });
        },
      },
    ])("$name in the arg.sessionId slot", ({ action, assert }) => {
      const state = workspaceReducer(workspaceReducer(initialState, setActiveSession("s1")), action);
      assert(state.bySession["s1"]);
    });
  });

  describe("interleaved sessions don't cross-contaminate", () => {
    it("two sessions' git statuses land in their own slots", () => {
      let state = workspaceReducer(initialState, setActiveSession("sA"));
      state = workspaceReducer(state, setActiveSession("sB"));
      // A's fetch arrives late (we're looking at B), then B's arrives.
      state = workspaceReducer(state, fulfilled(loadGitStatus, makeStatus({ session_id: "sA", branch: "A-branch" }), { sessionId: "sA" }));
      state = workspaceReducer(state, fulfilled(loadGitStatus, makeStatus({ session_id: "sB", branch: "B-branch" }), { sessionId: "sB" }));
      expect(state.bySession["sA"].status?.branch).toBe("A-branch");
      expect(state.bySession["sB"].status?.branch).toBe("B-branch");
      // activeSessionId still points at B.
      expect(state.activeSessionId).toBe("sB");
    });
  });

  describe("LRU eviction", () => {
    it("trims least-recently-touched entries past the cap", () => {
      let state: TestState = initialState;
      for (let i = 0; i < WORKSPACE_LRU_CAP + 3; i++) {
        state = workspaceReducer(state, setActiveSession(`s${i}`));
      }
      expect(Object.keys(state.bySession).length).toBe(WORKSPACE_LRU_CAP);
      expect(state.lruOrder.length).toBe(WORKSPACE_LRU_CAP);
      // First three (s0, s1, s2) evicted.
      expect(state.bySession["s0"]).toBeUndefined();
      expect(state.bySession["s1"]).toBeUndefined();
      expect(state.bySession["s2"]).toBeUndefined();
      // Most recent survives.
      expect(state.bySession[`s${WORKSPACE_LRU_CAP + 2}`]).toBeDefined();
    });

    it("touching an existing session moves it to the LRU tail", () => {
      let state = workspaceReducer(initialState, setActiveSession("sA"));
      state = workspaceReducer(state, setActiveSession("sB"));
      // Touch sA via a fulfilled write.
      state = workspaceReducer(state, fulfilled(loadGitStatus, makeStatus({ session_id: "sA" }), { sessionId: "sA" }));
      expect(state.lruOrder[state.lruOrder.length - 1]).toBe("sA");
    });

    it("late fulfilled for evicted session is a no-op", () => {
      let state: TestState = initialState;
      // Fill the cache past cap to evict sOld.
      state = workspaceReducer(state, setActiveSession("sOld"));
      for (let i = 0; i < WORKSPACE_LRU_CAP + 5; i++) {
        state = workspaceReducer(state, setActiveSession(`s${i}`));
      }
      expect(state.bySession["sOld"]).toBeUndefined();
      // Late response for sOld arrives — reducer must not resurrect the slot.
      state = workspaceReducer(state, fulfilled(loadGitStatus, makeStatus({ session_id: "sOld", branch: "stale" }), { sessionId: "sOld" }));
      expect(state.bySession["sOld"]).toBeUndefined();
    });
  });

  describe("removeSession.fulfilled", () => {
    it("drops the slot and LRU entry, and resets top-level ephemera", () => {
      let state = workspaceReducer(initialState, setActiveSession("s1"));
      state = workspaceReducer(state, fulfilled(loadGitStatus, makeStatus()));
      state = { ...state, actionOutput: "pushed", actionLoading: true, error: "stale" };
      state = workspaceReducer(state, fulfilled(removeSession, "s1", "s1"));
      expect(state.bySession["s1"]).toBeUndefined();
      expect(state.lruOrder).not.toContain("s1");
      expect(state.activeSessionId).toBeNull();
      expect(state.actionOutput).toBeNull();
      expect(state.actionLoading).toBe(false);
      expect(state.error).toBeNull();
    });

    it("does not touch activeSessionId when a different session is removed", () => {
      let state = workspaceReducer(initialState, setActiveSession("s1"));
      // Populate a cached slot for sOther.
      state = { ...state, bySession: { ...state.bySession, sOther: emptySessionWorkspace() }, lruOrder: [...state.lruOrder, "sOther"] };
      state = workspaceReducer(state, fulfilled(removeSession, "sOther", "sOther"));
      expect(state.activeSessionId).toBe("s1");
      expect(state.bySession["sOther"]).toBeUndefined();
      expect(state.bySession["s1"]).toBeDefined();
    });

    it("nulls the mirror when the active session is removed (focusListener re-syncs)", () => {
      // Two sessions, s1 active. Removing s1 nulls the mirror here; the
      // focusListener's removeSession handler will dispatch
      // setActiveSession(s2) which re-hydrates the mirror via the
      // setActiveSession extraReducer. This reducer on its own must not
      // leave the mirror pointing at a deleted id.
      let state = workspaceReducer(initialState, setActiveSession("s1"));
      state = { ...state, bySession: { ...state.bySession, s2: emptySessionWorkspace() }, lruOrder: [...state.lruOrder, "s2"] };
      state = workspaceReducer(state, fulfilled(removeSession, "s1", "s1"));
      expect(state.activeSessionId).toBeNull();
      expect(state.bySession["s1"]).toBeUndefined();
      // s2's slot survives until the focusListener's setActiveSession(s2)
      // dispatch lands — that's tested in focusListener.test.ts.
      expect(state.bySession["s2"]).toBeDefined();
    });
  });

  describe("active-slot addressed reducers", () => {
    it("selectFile writes to the active slot", () => {
      const state = workspaceReducer(stateWithActiveSession("s1"), selectFile("src/app.py"));
      expect(state.bySession["s1"].selectedFilePath).toBe("src/app.py");
    });

    it("selectFile(null) wipes file-viewer state in the active slot", () => {
      const prior = stateWithActiveSession("s1", {
        selectedFilePath: "old.ts",
        fileContent: { session_id: "s1", path: "old.ts", content: "x", language: "ts" },
        fileContentError: "prev",
      });
      const state = workspaceReducer(prior, selectFile(null));
      expect(state.bySession["s1"].selectedFilePath).toBeNull();
      expect(state.bySession["s1"].fileContent).toBeNull();
      expect(state.bySession["s1"].fileContentError).toBeNull();
    });

    it("clearDiff wipes selectedDiff in the active slot", () => {
      const prior = stateWithActiveSession("s1", {
        selectedDiff: { session_id: "s1", path: "a.ts", diff: "+x" },
      });
      const state = workspaceReducer(prior, clearDiff());
      expect(state.bySession["s1"].selectedDiff).toBeNull();
    });
  });

  describe("upsertGitStatus", () => {
    it("writes to an already-hydrated slot by sessionId", () => {
      const prior = stateWithActiveSession("sFg");
      // Hydrate a background slot too.
      prior.bySession["sBg"] = emptySessionWorkspace();
      prior.lruOrder.push("sBg");
      const status = makeStatus({ branch: "bg-branch" });
      const state = workspaceReducer(prior, upsertGitStatus({ sessionId: "sBg", status }));
      expect(state.bySession["sBg"].status).toEqual(status);
      // Foreground slot is untouched.
      expect(state.bySession["sFg"].status).toBeNull();
    });

    it("is a no-op when the target slot is not cached (evicted)", () => {
      const prior = stateWithActiveSession("sFg");
      const state = workspaceReducer(prior, upsertGitStatus({ sessionId: "sGone", status: makeStatus() }));
      expect(state.bySession["sGone"]).toBeUndefined();
    });

    it("drops the push when the viewed repo scope is not app", () => {
      const prior = stateWithActiveSession("s1", { status: makeStatus({ branch: "harness-view" }) });
      prior.repoScope = "harness";
      const state = workspaceReducer(prior, upsertGitStatus({ sessionId: "s1", status: makeStatus({ branch: "app" }) }));
      expect(state.bySession["s1"].status?.branch).toBe("harness-view");
    });
  });

  describe("sandbox file browser", () => {
    const containersPayload = {
      session_id: "s1",
      containers: [
        {
          id: "app",
          roots: [
            { id: "worktree", label: "Project worktree", path: "/app" },
            { id: "shared", label: "Shared scratchpad", path: "/shared" },
          ],
        },
        { id: "db", roots: [{ id: "data", label: "data", path: "/var/lib" }] },
      ],
    };

    function withContainers(): TestState {
      const state = workspaceReducer(initialState, setActiveSession("s1"));
      return workspaceReducer(state, fulfilled(loadSandboxContainers, containersPayload));
    }

    function dirListing(container: string, rootId: string, path: string, nodes: object[]): UnknownAction {
      return fulfilled(
        loadSandboxDir,
        { container, root: path, path, nodes },
        { sessionId: "s1", container, root: path, rootId, path },
      );
    }

    it("containers.fulfilled defaults to first container and its first root", () => {
      const slot = withContainers().bySession["s1"];
      expect(slot.sandboxContainersLoaded).toBe(true);
      expect(slot.sandboxContainer).toBe("app");
      expect(slot.sandboxRoot).toBe("worktree");
    });

    it("setSandboxContainer defaults the root and clears the browse state", () => {
      let state = withContainers();
      state = workspaceReducer(state, dirListing("app", "worktree", "/app", [{ name: "a", path: "/app/a", is_dir: false }]));
      state = workspaceReducer(state, setSandboxContainer("db"));
      const slot = state.bySession["s1"];
      expect(slot.sandboxContainer).toBe("db");
      expect(slot.sandboxRoot).toBe("data");
      expect(slot.sandboxDirCache).toEqual({});
      expect(slot.sandboxSelectedPath).toBeNull();
    });

    it("setSandboxRoot resets the browse state", () => {
      let state = withContainers();
      state = workspaceReducer(state, selectSandboxFile("/app/a"));
      state = workspaceReducer(state, setSandboxRoot("shared"));
      const slot = state.bySession["s1"];
      expect(slot.sandboxRoot).toBe("shared");
      expect(slot.sandboxSelectedPath).toBeNull();
    });

    it("loadSandboxDir.fulfilled caches nodes by path", () => {
      const state = workspaceReducer(withContainers(), dirListing("app", "worktree", "/app", [{ name: "x", path: "/app/x", is_dir: true }]));
      expect(state.bySession["s1"].sandboxDirCache["/app"]).toHaveLength(1);
    });

    it("loadSandboxDir.fulfilled ignores responses for a stale container/root", () => {
      const state = workspaceReducer(withContainers(), dirListing("db", "data", "/var/lib", [{ name: "x", path: "/var/lib/x", is_dir: false }]));
      // active container is still "app", so the "db" listing is dropped.
      expect(state.bySession["s1"].sandboxDirCache).toEqual({});
    });

    it("loadSandboxContent.fulfilled stores the content", () => {
      const state = workspaceReducer(
        withContainers(),
        fulfilled(loadSandboxContent, { container: "app", path: "/app/a", content: "hi", language: "text", truncated: false }),
      );
      expect(state.bySession["s1"].sandboxContent?.content).toBe("hi");
    });

    it("refreshSandbox clears the dir cache and content", () => {
      let state = workspaceReducer(withContainers(), dirListing("app", "worktree", "/app", [{ name: "a", path: "/app/a", is_dir: false }]));
      state = workspaceReducer(
        state,
        fulfilled(loadSandboxContent, { container: "app", path: "/app/a", content: "hi", language: "text", truncated: false }),
      );
      state = workspaceReducer(state, refreshSandbox());
      const slot = state.bySession["s1"];
      expect(slot.sandboxDirCache).toEqual({});
      expect(slot.sandboxContent).toBeNull();
    });

    it("loadSandboxDir.rejected with a starting sandbox shows starting, not an error", () => {
      const action = {
        type: loadSandboxDir.rejected.type,
        error: { name: SANDBOX_STARTING, message: "Sandbox is starting up." },
        meta: { arg: { sessionId: "s1" } },
      } as UnknownAction;
      const slot = workspaceReducer(withContainers(), action).bySession["s1"];
      expect(slot.sandboxStarting).toBe(true);
      expect(slot.sandboxError).toBeNull();
    });

    it("loadSandboxDir.rejected on a real failure reports the error", () => {
      const slot = workspaceReducer(
        withContainers(),
        rejected(loadSandboxDir, "container died"),
      ).bySession["s1"];
      expect(slot.sandboxStarting).toBe(false);
      expect(slot.sandboxError).toBe("container died");
    });
  });
});
