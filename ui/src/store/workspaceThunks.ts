import { createAsyncThunk } from "@reduxjs/toolkit";
import type { DiffMode, RepoScope } from "@/types/api";
import * as gitApi from "@/api/git";
import * as filesApi from "@/api/files";
import { dedupeCondition } from "@/store/dedupeThunk";

export interface SessionScopedArg {
  sessionId: string;
  // Bypass request dedupe: set by refetches that follow a mutation or a
  // repo-scope switch, whose answers an in-flight fetch cannot stand in for.
  force?: boolean;
}

// The Source Control panel's repo toggle is global viewing state; every git
// thunk reads it at dispatch time so callers never thread it by hand.
function repoScopeOf(getState: () => unknown): RepoScope {
  return (getState() as { workspace: { repoScope: RepoScope } }).workspace.repoScope;
}

export const loadRepos = createAsyncThunk(
  "workspace/loadRepos",
  async ({ sessionId }: SessionScopedArg) => gitApi.fetchGitRepos({ sessionId }),
  { condition: dedupeCondition<SessionScopedArg>("workspace/loadRepos", (arg) => arg.sessionId) },
);

export const loadGitStatus = createAsyncThunk(
  "workspace/loadGitStatus",
  async ({ sessionId }: SessionScopedArg, { getState }) => {
    const state = getState() as {
      workspace: { diffMode: DiffMode };
      sessions: { entities: Record<string, { base_branch?: string | null }> };
    };
    // "All changes" only makes sense against a base branch: the app repo
    // has one for worktree sessions, the harness worktree always has one,
    // and /shared never does (agents commit straight to its main).
    const repoScope = repoScopeOf(getState);
    const hasBase =
      repoScope === "harness" ? true :
      repoScope === "shared" ? false :
      !!state.sessions.entities[sessionId]?.base_branch;
    const mode = hasBase ? state.workspace.diffMode : "uncommitted";
    // Stamp the scope the request was made under so the reducer can discard
    // a response that arrives after the user switched repos.
    return Object.assign(await gitApi.fetchGitStatus({ sessionId, repoScope }, mode), { repoScope });
  },
  { condition: dedupeCondition<SessionScopedArg>("workspace/loadGitStatus", (arg) => arg.sessionId) },
);

export const loadBranches = createAsyncThunk(
  "workspace/loadBranches",
  async ({ sessionId }: SessionScopedArg) => gitApi.fetchGitBranches({ sessionId }),
  { condition: dedupeCondition<SessionScopedArg>("workspace/loadBranches", (arg) => arg.sessionId) },
);

export const checkoutBranch = createAsyncThunk(
  "workspace/checkoutBranch",
  async ({ sessionId, branch }: SessionScopedArg & { branch: string }, { dispatch }) => {
    const status = await gitApi.gitCheckout(branch, { sessionId });
    dispatch(loadBranches({ sessionId }));
    dispatch(loadGitLog({ sessionId, count: 50 }));
    return { sessionId, status };
  },
);

export const createBranch = createAsyncThunk(
  "workspace/createBranch",
  async ({ sessionId, name }: SessionScopedArg & { name: string }, { dispatch }) => {
    const status = await gitApi.gitCreateBranch(name, { sessionId });
    dispatch(loadBranches({ sessionId }));
    dispatch(loadGitLog({ sessionId, count: 50 }));
    return { sessionId, status };
  },
);

export const loadGitLog = createAsyncThunk(
  "workspace/loadGitLog",
  async ({ sessionId, count = 50 }: SessionScopedArg & { count?: number }, { getState }) => {
    const repoScope = repoScopeOf(getState);
    return Object.assign(await gitApi.fetchGitLog(count, { sessionId, repoScope }), { repoScope });
  },
  { condition: dedupeCondition<SessionScopedArg & { count?: number }>("workspace/loadGitLog", (arg) => arg.sessionId) },
);

export const loadChanges = createAsyncThunk(
  "workspace/loadChanges",
  async ({ sessionId, mode }: SessionScopedArg & { mode: DiffMode }, { getState }) => {
    const repoScope = repoScopeOf(getState);
    return Object.assign(await gitApi.fetchGitChanges(mode, { sessionId, repoScope }), { repoScope });
  },
  { condition: dedupeCondition<SessionScopedArg & { mode: DiffMode }>("workspace/loadChanges", (arg) => `${arg.sessionId}:${arg.mode}`) },
);

export const loadCommitDetail = createAsyncThunk(
  "workspace/loadCommitDetail",
  async ({ sessionId, hash }: SessionScopedArg & { hash: string }, { getState }) => {
    const repoScope = repoScopeOf(getState);
    return Object.assign(await gitApi.fetchGitCommitDetail(hash, { sessionId, repoScope }), { repoScope });
  },
  { condition: dedupeCondition<SessionScopedArg & { hash: string }>("workspace/loadCommitDetail", (arg) => `${arg.sessionId}:${arg.hash}`) },
);

export const loadDiff = createAsyncThunk(
  "workspace/loadDiff",
  async ({ sessionId, path, staged }: SessionScopedArg & { path: string; staged: boolean }, { getState }) => {
    const base = (getState() as { workspace: { diffMode: DiffMode } }).workspace.diffMode === "all";
    const repoScope = repoScopeOf(getState);
    return Object.assign(await gitApi.fetchGitDiff(path, staged, { sessionId, repoScope }, base), { repoScope });
  },
  { condition: dedupeCondition<SessionScopedArg & { path: string; staged: boolean }>("workspace/loadDiff", (arg) => `${arg.sessionId}:${arg.path}:${arg.staged}`) },
);

export const stageFiles = createAsyncThunk(
  "workspace/stage",
  async ({ sessionId, paths }: SessionScopedArg & { paths: string[] }, { dispatch, getState }) => {
    await gitApi.gitStageFiles(paths, { sessionId, repoScope: repoScopeOf(getState) });
    dispatch(loadGitStatus({ sessionId, force: true }));
  },
);

export const unstageFiles = createAsyncThunk(
  "workspace/unstage",
  async ({ sessionId, paths }: SessionScopedArg & { paths: string[] }, { dispatch, getState }) => {
    await gitApi.gitUnstageFiles(paths, { sessionId, repoScope: repoScopeOf(getState) });
    dispatch(loadGitStatus({ sessionId, force: true }));
  },
);

export const discardFiles = createAsyncThunk(
  "workspace/discard",
  async ({ sessionId, paths }: SessionScopedArg & { paths: string[] }, { dispatch, getState }) => {
    await gitApi.gitDiscardFiles(paths, { sessionId, repoScope: repoScopeOf(getState) });
    dispatch(loadGitStatus({ sessionId, force: true }));
  },
);

export const loadFileTree = createAsyncThunk(
  "workspace/loadFileTree",
  async ({ sessionId }: SessionScopedArg) => filesApi.fetchFileTree({ sessionId }),
  { condition: dedupeCondition<SessionScopedArg>("workspace/loadFileTree", (arg) => arg.sessionId) },
);

export const loadFileContent = createAsyncThunk(
  "workspace/loadFileContent",
  async ({ sessionId, path }: SessionScopedArg & { path: string }) =>
    filesApi.fetchFileContent(path, { sessionId }),
  { condition: dedupeCondition<SessionScopedArg & { path: string }>("workspace/loadFileContent", (arg) => `${arg.sessionId}:${arg.path}`) },
);

interface SandboxDirArg extends SessionScopedArg {
  container: string;
  root: string;
  rootId: string;
  path: string | null;
}

interface SandboxFileArg extends SessionScopedArg {
  container: string;
  root: string;
  path: string;
}

export const loadSandboxContainers = createAsyncThunk(
  "workspace/loadSandboxContainers",
  async ({ sessionId }: SessionScopedArg) => filesApi.fetchSandboxContainers({ sessionId }),
  { condition: dedupeCondition<SessionScopedArg>("workspace/loadSandboxContainers", (arg) => arg.sessionId) },
);

export const loadSandboxDir = createAsyncThunk(
  "workspace/loadSandboxDir",
  async ({ sessionId, container, root, path }: SandboxDirArg) =>
    filesApi.fetchSandboxTree(container, root, path, { sessionId }),
);

export const loadSandboxContent = createAsyncThunk(
  "workspace/loadSandboxContent",
  async ({ sessionId, container, root, path }: SandboxFileArg) =>
    filesApi.fetchSandboxContent(container, root, path, { sessionId }),
);
