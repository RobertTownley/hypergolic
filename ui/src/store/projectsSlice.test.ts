import { describe, it, expect, vi, beforeEach } from "vitest";
import projectsReducer, {
  loadProjects,
  loadProjectBranches,
  loadProjectRoles,
  selectProjectBranches,
  selectProjectRoles,
} from "./projectsSlice";
import { makeSliceStore, deferred, pending, fulfilled, rejected } from "@/test/store";
import { makeProject } from "@/test/fixtures";
import * as projectsApi from "@/api/projects";
import * as sessionsApi from "@/api/sessions";
import type { RoleInfo } from "@/types/api";

vi.mock("@/api/projects", () => ({
  fetchProjects: vi.fn(),
  fetchProjectBranches: vi.fn(),
}));

vi.mock("@/api/sessions", () => ({
  fetchRoles: vi.fn(),
}));

const fetchProjectBranches = vi.mocked(projectsApi.fetchProjectBranches);
const fetchRoles = vi.mocked(sessionsApi.fetchRoles);

const initialState = {
  entities: {},
  ids: [],
  initialized: false,
  loading: false,
  error: null,
  branchesByProjectId: {},
  rolesByProjectId: {},
};

const sampleRoles: RoleInfo[] = [
  { id: "generalist", name: "Generalist", source: "built-in" },
  { id: "reviewer", name: "Reviewer", source: "project" },
];

const branchesPending = (projectId: string) => pending(loadProjectBranches, { projectId });
const rolesPending = (projectId: string) => pending(loadProjectRoles, { projectId });
const makeStore = () => makeSliceStore({ projects: projectsReducer });

beforeEach(() => {
  fetchProjectBranches.mockReset();
  fetchRoles.mockReset();
});

describe("projectsSlice", () => {
  it("should return the initial state", () => {
    expect(projectsReducer(undefined, { type: "unknown" })).toEqual(initialState);
  });

  describe("loadProjects", () => {
    it("should set loading on pending", () => {
      const action = pending(loadProjects);
      const state = projectsReducer(initialState, action);
      expect(state.loading).toBe(true);
      expect(state.error).toBeNull();
    });

    it("should populate entities on fulfilled", () => {
      const projects = [makeProject({ id: "p1", name: "Alpha" }), makeProject({ id: "p2", name: "Beta" })];
      const action = fulfilled(loadProjects, projects);
      const state = projectsReducer(initialState, action);
      expect(state.loading).toBe(false);
      expect(state.initialized).toBe(true);
      expect(state.ids).toEqual(["p1", "p2"]);
      expect(state.entities["p1"].name).toBe("Alpha");
    });

    it("should set error on rejected", () => {
      const action = rejected(loadProjects, "Network error");
      const state = projectsReducer(initialState, action);
      expect(state.loading).toBe(false);
      expect(state.initialized).toBe(true);
      expect(state.error).toBe("Network error");
    });
  });

  describe("loadProjectBranches reducers", () => {
    it("creates a loading record on pending", () => {
      const state = projectsReducer(initialState, branchesPending("p1"));
      expect(state.branchesByProjectId["p1"]).toEqual({
        data: { branches: [], current: null },
        loading: true,
        loaded: false,
        error: null,
      });
    });

    it("keeps previously loaded branches visible while refetching", () => {
      const prior = {
        ...initialState,
        branchesByProjectId: {
          p1: {
            data: { branches: ["main", "dev"], current: "main" },
            loading: false,
            loaded: true,
            error: null,
          },
        },
      };
      const state = projectsReducer(prior, branchesPending("p1"));
      expect(state.branchesByProjectId["p1"]).toEqual({
        data: { branches: ["main", "dev"], current: "main" },
        loading: true,
        loaded: true,
        error: null,
      });
    });

    it("stores branches and current on fulfilled", () => {
      let state = projectsReducer(initialState, branchesPending("p1"));
      state = projectsReducer(state, fulfilled(loadProjectBranches, { project_id: "p1", branches: ["main", "dev"], current: "dev" }, { projectId: "p1" }));
      expect(state.branchesByProjectId["p1"]).toEqual({
        data: { branches: ["main", "dev"], current: "dev" },
        loading: false,
        loaded: true,
        error: null,
      });
    });

    it("normalizes an empty current branch to null on fulfilled", () => {
      const state = projectsReducer(initialState, fulfilled(loadProjectBranches, { project_id: "p1", branches: [], current: "" }, { projectId: "p1" }));
      expect(state.branchesByProjectId["p1"].data.current).toBeNull();
    });

    it("records the error on rejected and keeps prior branches", () => {
      let state = projectsReducer(initialState, fulfilled(loadProjectBranches, { project_id: "p1", branches: ["main"], current: "main" }, { projectId: "p1" }));
      state = projectsReducer(state, branchesPending("p1"));
      state = projectsReducer(state, rejected(loadProjectBranches, "boom", { projectId: "p1" }));
      expect(state.branchesByProjectId["p1"]).toEqual({
        data: { branches: ["main"], current: "main" },
        loading: false,
        loaded: true,
        error: "boom",
      });
    });

    it("scopes records per project", () => {
      let state = projectsReducer(initialState, branchesPending("p1"));
      state = projectsReducer(state, branchesPending("p2"));
      state = projectsReducer(state, fulfilled(loadProjectBranches, { project_id: "p2", branches: ["trunk"], current: "trunk" }, { projectId: "p2" }));
      expect(state.branchesByProjectId["p1"].loading).toBe(true);
      expect(state.branchesByProjectId["p2"]).toEqual({
        data: { branches: ["trunk"], current: "trunk" },
        loading: false,
        loaded: true,
        error: null,
      });
    });
  });

  describe("loadProjectRoles reducers", () => {
    it("creates a loading record on pending", () => {
      const state = projectsReducer(initialState, rolesPending("p1"));
      expect(state.rolesByProjectId["p1"]).toEqual({
        data: [],
        loading: true,
        loaded: false,
        error: null,
      });
    });

    it("stores roles and marks loaded on fulfilled", () => {
      let state = projectsReducer(initialState, rolesPending("p1"));
      state = projectsReducer(state, fulfilled(loadProjectRoles, sampleRoles, { projectId: "p1" }));
      expect(state.rolesByProjectId["p1"]).toEqual({
        data: sampleRoles,
        loading: false,
        loaded: true,
        error: null,
      });
    });

    it("records the error and leaves loaded false on rejected", () => {
      let state = projectsReducer(initialState, rolesPending("p1"));
      state = projectsReducer(state, rejected(loadProjectRoles, "no roles", { projectId: "p1" }));
      expect(state.rolesByProjectId["p1"]).toEqual({
        data: [],
        loading: false,
        loaded: false,
        error: "no roles",
      });
    });
  });

  describe("loadProjectBranches thunk (dedupe)", () => {
    it("dedupes concurrent dispatches for the same project", async () => {
      const { promise, resolve } = deferred<projectsApi.ProjectBranchesResponse>();
      fetchProjectBranches.mockReturnValue(promise);

      const store = makeStore();
      const p1 = store.dispatch(loadProjectBranches({ projectId: "p1" }));
      const p2 = store.dispatch(loadProjectBranches({ projectId: "p1" }));

      resolve({ project_id: "p1", branches: ["main"], current: "main" });
      await p1;
      await p2;

      expect(fetchProjectBranches).toHaveBeenCalledTimes(1);
      expect(store.getState().projects.branchesByProjectId["p1"].data.branches).toEqual(["main"]);
    });

    it("does NOT dedupe concurrent dispatches for different projects", async () => {
      const a = deferred<projectsApi.ProjectBranchesResponse>();
      const b = deferred<projectsApi.ProjectBranchesResponse>();
      fetchProjectBranches.mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise);

      const store = makeStore();
      const pA = store.dispatch(loadProjectBranches({ projectId: "p1" }));
      const pB = store.dispatch(loadProjectBranches({ projectId: "p2" }));

      a.resolve({ project_id: "p1", branches: ["main"], current: "main" });
      b.resolve({ project_id: "p2", branches: ["trunk"], current: "trunk" });
      await pA;
      await pB;

      expect(fetchProjectBranches).toHaveBeenCalledTimes(2);
      expect(store.getState().projects.branchesByProjectId["p2"].data.current).toBe("trunk");
    });

    it("refetches (branches are not cached forever) once the prior call settles", async () => {
      fetchProjectBranches.mockResolvedValue({ project_id: "p1", branches: ["main"], current: "main" });
      const store = makeStore();

      await store.dispatch(loadProjectBranches({ projectId: "p1" }));
      await store.dispatch(loadProjectBranches({ projectId: "p1" }));

      expect(fetchProjectBranches).toHaveBeenCalledTimes(2);
    });

    it("allows a retry after a rejection", async () => {
      fetchProjectBranches
        .mockRejectedValueOnce(new Error("boom"))
        .mockResolvedValueOnce({ project_id: "p1", branches: ["main"], current: "main" });
      const store = makeStore();

      await store.dispatch(loadProjectBranches({ projectId: "p1" }));
      expect(store.getState().projects.branchesByProjectId["p1"].error).toBe("boom");

      await store.dispatch(loadProjectBranches({ projectId: "p1" }));
      expect(fetchProjectBranches).toHaveBeenCalledTimes(2);
      expect(store.getState().projects.branchesByProjectId["p1"].error).toBeNull();
    });

    it("unwrap resolves with the fetched payload for imperative callers", async () => {
      fetchProjectBranches.mockResolvedValue({ project_id: "p1", branches: ["main", "dev"], current: "dev" });
      const store = makeStore();
      const payload = await store.dispatch(loadProjectBranches({ projectId: "p1" })).unwrap();
      expect(payload).toEqual({ project_id: "p1", branches: ["main", "dev"], current: "dev" });
    });
  });

  describe("loadProjectRoles thunk (skip-when-loaded + dedupe)", () => {
    it("dedupes concurrent dispatches for the same project", async () => {
      const { promise, resolve } = deferred<RoleInfo[]>();
      fetchRoles.mockReturnValue(promise);

      const store = makeStore();
      const p1 = store.dispatch(loadProjectRoles({ projectId: "p1" }));
      const p2 = store.dispatch(loadProjectRoles({ projectId: "p1" }));

      resolve(sampleRoles);
      await p1;
      await p2;

      expect(fetchRoles).toHaveBeenCalledTimes(1);
    });

    it("skips the fetch entirely once roles are loaded", async () => {
      fetchRoles.mockResolvedValue(sampleRoles);
      const store = makeStore();

      await store.dispatch(loadProjectRoles({ projectId: "p1" }));
      await store.dispatch(loadProjectRoles({ projectId: "p1" }));

      expect(fetchRoles).toHaveBeenCalledTimes(1);
      expect(store.getState().projects.rolesByProjectId["p1"].data).toEqual(sampleRoles);
    });

    it("still fetches for a different project", async () => {
      fetchRoles.mockResolvedValue(sampleRoles);
      const store = makeStore();

      await store.dispatch(loadProjectRoles({ projectId: "p1" }));
      await store.dispatch(loadProjectRoles({ projectId: "p2" }));

      expect(fetchRoles).toHaveBeenCalledTimes(2);
      expect(fetchRoles).toHaveBeenNthCalledWith(1, "p1");
      expect(fetchRoles).toHaveBeenNthCalledWith(2, "p2");
    });

    it("retries after a rejection (loaded stays false)", async () => {
      fetchRoles.mockRejectedValueOnce(new Error("fail")).mockResolvedValueOnce(sampleRoles);
      const store = makeStore();

      await store.dispatch(loadProjectRoles({ projectId: "p1" }));
      expect(store.getState().projects.rolesByProjectId["p1"].loaded).toBe(false);

      await store.dispatch(loadProjectRoles({ projectId: "p1" }));
      expect(fetchRoles).toHaveBeenCalledTimes(2);
      expect(store.getState().projects.rolesByProjectId["p1"].loaded).toBe(true);
    });
  });

  describe("selectors", () => {
    it("selectProjectBranches returns the record for a project", () => {
      const entry = { data: { branches: ["main"], current: "main" }, loading: false, loaded: true, error: null };
      const state = { projects: { ...initialState, branchesByProjectId: { p1: entry } } };
      expect(selectProjectBranches(state, "p1")).toBe(entry);
    });

    it("selectProjectBranches falls back to a stable empty record", () => {
      const state = { projects: initialState };
      const first = selectProjectBranches(state, "missing");
      expect(first).toEqual({ data: { branches: [], current: null }, loading: false, loaded: false, error: null });
      expect(selectProjectBranches(state, null)).toBe(first);
    });

    it("selectProjectRoles returns the record for a project", () => {
      const entry = { data: sampleRoles, loading: false, loaded: true, error: null };
      const state = { projects: { ...initialState, rolesByProjectId: { p1: entry } } };
      expect(selectProjectRoles(state, "p1")).toBe(entry);
    });

    it("selectProjectRoles falls back to a stable empty record", () => {
      const state = { projects: initialState };
      const first = selectProjectRoles(state, "missing");
      expect(first).toEqual({ data: [], loading: false, loaded: false, error: null });
      expect(selectProjectRoles(state, undefined)).toBe(first);
    });
  });
});
