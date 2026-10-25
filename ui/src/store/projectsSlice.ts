import { createSlice, createAsyncThunk } from "@reduxjs/toolkit";
import type { Project, RoleInfo } from "@/types/api";
import * as api from "@/api/projects";
import { fetchRoles } from "@/api/sessions";
import { dedupeCondition } from "@/store/dedupeThunk";
import { addKeyedCases, asyncEntry, type AsyncEntry } from "@/store/asyncMap";
import { setAll } from "@/store/entities";

// Project-scoped branch listing, used BEFORE a session exists (picking a base
// branch for a new session). Session-scoped branches live in workspaceSlice.
export type ProjectBranches = AsyncEntry<{
  branches: string[];
  current: string | null;
}>;

// Roles are static per project: once loaded, consumers never refetch.
export type ProjectRoles = AsyncEntry<RoleInfo[]>;

interface ProjectsState {
  entities: Record<string, Project>;
  ids: string[];
  initialized: boolean;
  loading: boolean;
  error: string | null;
  branchesByProjectId: Record<string, ProjectBranches>;
  rolesByProjectId: Record<string, ProjectRoles>;
}

const initialState: ProjectsState = {
  entities: {},
  ids: [],
  initialized: false,
  loading: false,
  error: null,
  branchesByProjectId: {},
  rolesByProjectId: {},
};

export const loadProjects = createAsyncThunk("projects/load", async () => {
  return api.fetchProjects();
});

export interface ProjectScopedArg {
  projectId: string;
}

export const loadProjectBranches = createAsyncThunk(
  "projects/loadBranches",
  async ({ projectId }: ProjectScopedArg) => api.fetchProjectBranches(projectId),
  { condition: dedupeCondition<ProjectScopedArg>("projects/loadBranches", (arg) => arg.projectId) },
);

const dedupeLoadRoles = dedupeCondition<ProjectScopedArg>(
  "projects/loadRoles",
  (arg) => arg.projectId,
);

export const loadProjectRoles = createAsyncThunk(
  "projects/loadRoles",
  async ({ projectId }: ProjectScopedArg) => fetchRoles(projectId),
  {
    condition: (arg: ProjectScopedArg, { getState }) => {
      // Roles are static per project — skip entirely once loaded.
      const { projects } = getState() as { projects: ProjectsState };
      if (projects.rolesByProjectId[arg.projectId]?.loaded) return false;
      return dedupeLoadRoles(arg);
    },
  },
);

const projectsSlice = createSlice({
  name: "projects",
  initialState,
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(loadProjects.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(loadProjects.fulfilled, (state, action) => {
        state.loading = false;
        state.initialized = true;
        setAll(state, action.payload);
      })
      .addCase(loadProjects.rejected, (state, action) => {
        state.loading = false;
        state.initialized = true;
        state.error = action.error.message ?? "Failed to load projects";
      });
    addKeyedCases(builder, loadProjectBranches, {
      entry: (s: ProjectsState, k) =>
        (s.branchesByProjectId[k] ??= asyncEntry({ branches: [], current: null })),
      key: (arg) => arg.projectId,
      data: (payload) => ({ branches: payload.branches, current: payload.current || null }),
      failMessage: "Failed to load project branches",
    });
    addKeyedCases(builder, loadProjectRoles, {
      entry: (s: ProjectsState, k) => (s.rolesByProjectId[k] ??= asyncEntry<RoleInfo[]>([])),
      key: (arg) => arg.projectId,
      data: (payload) => payload,
      failMessage: "Failed to load roles",
    });
  },
});

// Stable fallbacks so selectors stay referentially equal across renders.
const EMPTY_PROJECT_BRANCHES: ProjectBranches = asyncEntry({ branches: [], current: null });
const EMPTY_PROJECT_ROLES: ProjectRoles = asyncEntry<RoleInfo[]>([]);

export const selectProjectBranches = (
  state: { projects: ProjectsState },
  projectId: string | null | undefined,
): ProjectBranches =>
  (projectId ? state.projects.branchesByProjectId[projectId] : undefined) ??
  EMPTY_PROJECT_BRANCHES;

export const selectProjectRoles = (
  state: { projects: ProjectsState },
  projectId: string | null | undefined,
): ProjectRoles =>
  (projectId ? state.projects.rolesByProjectId[projectId] : undefined) ?? EMPTY_PROJECT_ROLES;

export default projectsSlice.reducer;
