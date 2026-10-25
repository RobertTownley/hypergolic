import { describe, it, expect, vi, beforeEach } from "vitest";
import { openHarnessSession, HARNESS_PROJECT_ID } from "./openHarnessSession";
import * as sessionsApi from "@/api/sessions";
import * as projectsApi from "@/api/projects";
import { createTestStore, makeSession, type TestStore } from "@/test/fixtures";

vi.mock("@/api/sessions", () => ({
  fetchSessions: vi.fn(),
  createSession: vi.fn(),
}));

vi.mock("@/api/projects", () => ({
  fetchProjects: vi.fn(),
  fetchProjectBranches: vi.fn(),
}));

const fetchSessions = vi.mocked(sessionsApi.fetchSessions);
const createSession = vi.mocked(sessionsApi.createSession);
const fetchProjectBranches = vi.mocked(projectsApi.fetchProjectBranches);

describe("openHarnessSession", () => {
  let store: TestStore;

  beforeEach(() => {
    fetchSessions.mockReset();
    createSession.mockReset();
    fetchProjectBranches.mockReset();
    store = createTestStore();
  });

  it("focuses an existing empty session and does not call fetchProjectBranches", async () => {
    const empty = makeSession({ id: "empty-1", message_count: 0, project_id: HARNESS_PROJECT_ID });
    fetchSessions.mockResolvedValue([
      makeSession({ id: "used-1", message_count: 5, project_id: HARNESS_PROJECT_ID }),
      empty,
    ]);

    await openHarnessSession(store.dispatch);

    expect(fetchSessions).toHaveBeenCalledWith(HARNESS_PROJECT_ID);
    expect(fetchProjectBranches).not.toHaveBeenCalled();
    expect(createSession).not.toHaveBeenCalled();
    expect(store.getState().sessions.activeSessionId).toBe("empty-1");
    expect(store.getState().ui.leftPanelCollapsed).toBe(false);
    expect(store.getState().ui.leftTab).toBe("git");
  });

  it.each([
    ["no empty session exists", [makeSession({ id: "used-1", message_count: 3, project_id: HARNESS_PROJECT_ID })]],
    ["the project has no sessions at all", []],
  ])("creates a new session when %s", async (_name, sessions) => {
    fetchSessions.mockResolvedValue(sessions);
    fetchProjectBranches.mockResolvedValue({ project_id: HARNESS_PROJECT_ID, current: "main", branches: ["main"] });
    createSession.mockResolvedValue(
      makeSession({ id: "new-session", message_count: 0, project_id: HARNESS_PROJECT_ID }),
    );

    await openHarnessSession(store.dispatch);

    expect(fetchProjectBranches).toHaveBeenCalledWith(HARNESS_PROJECT_ID);
    expect(createSession).toHaveBeenCalledWith(HARNESS_PROJECT_ID, "main", "High", "generalist");
    // setActiveSession must be dispatched with the new session id — the
    // derived selectActiveProjectId picks up the project from it.
    expect(store.getState().sessions.activeSessionId).toBe("new-session");
    expect(store.getState().ui.leftPanelCollapsed).toBe(false);
    expect(store.getState().ui.leftTab).toBe("git");
    // The branch lookup now flows through the store instead of being discarded.
    expect(store.getState().projects.branchesByProjectId[HARNESS_PROJECT_ID]).toEqual({
      data: { branches: ["main"], current: "main" },
      loading: false,
      loaded: true,
      error: null,
    });
  });

  it("throws when there are no branches", async () => {
    fetchSessions.mockResolvedValue([]);
    fetchProjectBranches.mockResolvedValue({ project_id: HARNESS_PROJECT_ID, current: "", branches: [] });

    await expect(openHarnessSession(store.dispatch)).rejects.toThrow(/no git branch/i);
    expect(createSession).not.toHaveBeenCalled();
    expect(store.getState().sessions.activeSessionId).toBeNull();
  });
});
