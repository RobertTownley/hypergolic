import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { Provider } from "react-redux";
import { useNewSessionModal } from "./useNewSessionModal";
import { loadSystemConfig } from "@/store/uiSlice";
import { setActiveSession, upsertSession } from "@/store/sessionsSlice";
import { createTestStore, makeProject, makeSession, type TestStore } from "@/test/fixtures";
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

const sampleRoles: RoleInfo[] = [
  { id: "generalist", name: "Generalist", source: "built-in" },
  { id: "reviewer", name: "Reviewer", source: "project" },
];

function makeStore(activeProject: string | null = null): TestStore {
  const projects = [makeProject({ id: "p1", name: "Alpha" }), makeProject({ id: "p2", name: "Beta" })];
  const store = createTestStore({
    projects: {
      entities: Object.fromEntries(projects.map((p) => [p.id, p])),
      ids: projects.map((p) => p.id),
      initialized: true,
      loading: false,
      error: null,
      branchesByProjectId: {},
      rolesByProjectId: {},
    },
  });
  if (activeProject) {
    store.dispatch(upsertSession(makeSession({ id: `sess-${activeProject}`, project_id: activeProject })));
    store.dispatch(setActiveSession(`sess-${activeProject}`));
  }
  return store;
}

function wrapper(store: TestStore) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <Provider store={store}>{children}</Provider>;
  };
}

function renderModalHook(store: TestStore) {
  return renderHook(() => useNewSessionModal(vi.fn()), { wrapper: wrapper(store) });
}

const flush = () => act(async () => {});

const configArrived = (tier: "Low" | "Medium" | "High" | "Extra High") =>
  loadSystemConfig.fulfilled({ default_model_tier: tier, truncate_token_threshold: 40000 }, "req-1");

beforeEach(() => {
  fetchProjectBranches.mockReset();
  fetchRoles.mockReset();
  fetchProjectBranches.mockImplementation(async (projectId: string) => ({
    project_id: projectId,
    branches: projectId === "p1" ? ["main", "dev"] : ["trunk"],
    current: projectId === "p1" ? "main" : "trunk",
  }));
  fetchRoles.mockResolvedValue(sampleRoles);
});

describe("useNewSessionModal — override-or-derive", () => {
  it("modelTier follows the store default until the user overrides it", async () => {
    const store = makeStore();
    const { result } = renderModalHook(store);

    // Config not loaded yet — fallback tier.
    expect(result.current.modelTier).toBe("High");

    // Config resolves AFTER the modal opened; the store value must flow through.
    act(() => { store.dispatch(configArrived("Medium")); });
    expect(result.current.modelTier).toBe("Medium");

    // An explicit user pick wins…
    act(() => { result.current.setModelTier("Low"); });
    expect(result.current.modelTier).toBe("Low");

    // …and is not clobbered by later store updates.
    act(() => { store.dispatch(configArrived("Extra High")); });
    expect(result.current.modelTier).toBe("Low");
  });

  it("selectedProjectId follows the active project until the user overrides it", async () => {
    const store = makeStore("p1");
    const { result } = renderModalHook(store);
    await flush();

    expect(result.current.selectedProjectId).toBe("p1");

    // Active project changes in the store — the modal tracks it.
    act(() => {
      store.dispatch(upsertSession(makeSession({ id: "sess-p2", project_id: "p2" })));
      store.dispatch(setActiveSession("sess-p2"));
    });
    await flush();
    expect(result.current.selectedProjectId).toBe("p2");

    // An explicit pick sticks even if the active project changes again.
    act(() => { result.current.setSelectedProjectId("p1"); });
    await flush();
    act(() => { store.dispatch(setActiveSession("sess-p2")); });
    expect(result.current.selectedProjectId).toBe("p1");
  });
});

describe("useNewSessionModal — store-backed roles and branches", () => {
  it("loads roles and branches via the store and derives the base branch", async () => {
    const store = makeStore("p1");
    const { result } = renderModalHook(store);
    await flush();

    expect(fetchRoles).toHaveBeenCalledTimes(1);
    expect(fetchRoles).toHaveBeenCalledWith("p1");
    expect(fetchProjectBranches).toHaveBeenCalledTimes(1);
    expect(fetchProjectBranches).toHaveBeenCalledWith("p1");

    expect(result.current.roleOptions).toEqual([
      { value: "generalist", label: "Generalist" },
      { value: "reviewer", label: "Reviewer" },
    ]);
    expect(result.current.branches).toEqual(["main", "dev"]);
    expect(result.current.baseBranch).toBe("main");
    expect(result.current.branchesLoading).toBe(false);
    expect(result.current.canSubmit).toBe(true);
  });

  it("does not refetch roles on re-open (static per project); branches refresh", async () => {
    const store = makeStore("p1");
    const first = renderModalHook(store);
    await flush();
    first.unmount();

    const second = renderModalHook(store);
    await flush();

    expect(fetchRoles).toHaveBeenCalledTimes(1);
    expect(fetchProjectBranches).toHaveBeenCalledTimes(2);
    // Cached roles are available immediately on the second open.
    expect(second.result.current.roleOptions.length).toBe(2);
  });

  it("switching projects resets role and base-branch overrides", async () => {
    const store = makeStore("p1");
    const { result } = renderModalHook(store);
    await flush();

    act(() => {
      result.current.setBaseBranch("dev");
      result.current.setRole("reviewer");
    });
    expect(result.current.baseBranch).toBe("dev");
    expect(result.current.role).toBe("reviewer");

    act(() => { result.current.setSelectedProjectId("p2"); });
    await flush();

    expect(result.current.selectedProjectId).toBe("p2");
    expect(result.current.role).toBe("generalist");
    expect(result.current.baseBranch).toBe("trunk");
    expect(result.current.branches).toEqual(["trunk"]);
    expect(fetchProjectBranches).toHaveBeenCalledWith("p2");
  });
});
