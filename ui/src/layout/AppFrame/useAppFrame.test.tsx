import { describe, it, expect, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { Provider } from "react-redux";
import { useAppFrame } from "./useAppFrame";
import { setLeftTab } from "@/store/uiSlice";
import { setActiveSession, upsertSession } from "@/store/sessionsSlice";
import { createTestStore, makeSession, type TestStore } from "@/test/fixtures";

vi.mock("@/api/sessions", () => ({
  fetchSessions: vi.fn().mockResolvedValue([]),
}));
vi.mock("@/api/projects", () => ({
  fetchProjects: vi.fn().mockResolvedValue([]),
}));
vi.mock("@/api/git", () => ({
  fetchGitStatus: vi.fn().mockResolvedValue({ session_id: "s-1", branch: "main", ahead: 0, behind: 0, staged: [], unstaged: [], untracked: [], all_changes: [] }),
  fetchGitBranches: vi.fn().mockResolvedValue({ session_id: "s-1", branches: [], current: "main" }),
  fetchGitLog: vi.fn().mockResolvedValue({ session_id: "s-1", entries: [] }),
}));
vi.mock("@/api/files", () => ({
  fetchFileTree: vi.fn().mockResolvedValue({ session_id: "s-1", root: "/tmp", tree: [] }),
}));

function wrapper(store: TestStore) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <Provider store={store}>{children}</Provider>;
  };
}

describe("useAppFrame session-scoped tab redirect", () => {
  // uiSlice default is "git", so the first case also covers the mount default.
  it.each(["git", "files", "help"] as const)(
    "redirects %s \u2192 projects when no session is active on mount",
    (tab) => {
      const store = createTestStore();
      store.dispatch(setLeftTab(tab));
      renderHook(() => useAppFrame(), { wrapper: wrapper(store) });
      expect(store.getState().ui.leftTab).toBe("projects");
    },
  );

  it("does not redirect non-session tabs", () => {
    const store = createTestStore();
    store.dispatch(setLeftTab("analytics"));
    renderHook(() => useAppFrame(), { wrapper: wrapper(store) });
    expect(store.getState().ui.leftTab).toBe("analytics");
  });

  it("leaves git alone while a session is active, then redirects when it clears", () => {
    const store = createTestStore();
    store.dispatch(upsertSession(makeSession({ id: "s-1" })));
    store.dispatch(setActiveSession("s-1"));
    expect(store.getState().ui.leftTab).toBe("git");
    renderHook(() => useAppFrame(), { wrapper: wrapper(store) });
    expect(store.getState().ui.leftTab).toBe("git");

    act(() => {
      store.dispatch(setActiveSession(null));
    });
    expect(store.getState().ui.leftTab).toBe("projects");
  });
});
