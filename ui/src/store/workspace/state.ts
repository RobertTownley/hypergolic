import type {
  GitStatusResponse,
  GitDiffResponse,
  GitLogEntry,
  GitReviewFile,
  GitCommitDetail,
  FileNode,
  FileContentResponse,
  DiffMode,
  RepoScope,
  SandboxContainer,
  SandboxNode,
  SandboxContentResponse,
} from "@/types/api";

export type FileSource = "host" | "sandbox";

export interface SessionWorkspace {
  status: GitStatusResponse | null;
  branches: string[];
  tree: FileNode[];
  root: string | null;
  logEntries: GitLogEntry[];
  changes: GitReviewFile[] | null;
  // Diff mode the cached ``changes`` were fetched with; a mode switch clears
  // the list so the panel never shows the other mode's files while refetching.
  changesMode: DiffMode | null;
  // Which repo scopes exist for this session; null until fetched.
  availableRepos: Record<RepoScope, boolean> | null;
  changesLoading: boolean;
  commitDetail: GitCommitDetail | null;
  selectedDiff: GitDiffResponse | null;
  selectedFilePath: string | null;
  fileContent: FileContentResponse | null;
  expandedFilePaths: string[];
  loading: boolean;
  branchesLoading: boolean;
  treeLoading: boolean;
  logLoading: boolean;
  commitDetailLoading: boolean;
  diffLoading: boolean;
  fileContentLoading: boolean;
  statusError: string | null;
  treeError: string | null;
  fileContentError: string | null;
  // Sandbox file browser: per-session selection + lazy dir cache.
  sandboxContainers: SandboxContainer[];
  sandboxContainersLoaded: boolean;
  sandboxContainer: string | null;
  sandboxRoot: string | null;
  sandboxDirCache: Record<string, SandboxNode[]>;
  sandboxExpandedPaths: string[];
  sandboxSelectedPath: string | null;
  sandboxContent: SandboxContentResponse | null;
  sandboxLoading: boolean;
  sandboxContentLoading: boolean;
  sandboxError: string | null;
  sandboxContentError: string | null;
  // The container is still coming up; the browser shows "starting" and retries.
  sandboxStarting: boolean;
}

export interface WorkspaceState {
  bySession: Record<string, SessionWorkspace>;
  lruOrder: string[];
  activeSessionId: string | null;
  actionLoading: boolean;
  actionOutput: string | null;
  error: string | null;
  // Global viewing preferences, not session state.
  diffMode: DiffMode;
  repoScope: RepoScope;
  fileSource: FileSource;
}

export const WORKSPACE_LRU_CAP = 512;

export function emptySessionWorkspace(): SessionWorkspace {
  return {
    status: null,
    branches: [],
    tree: [],
    root: null,
    logEntries: [],
    changes: null,
    changesMode: null,
    availableRepos: null,
    changesLoading: false,
    commitDetail: null,
    selectedDiff: null,
    selectedFilePath: null,
    fileContent: null,
    expandedFilePaths: [],
    loading: false,
    branchesLoading: false,
    treeLoading: false,
    logLoading: false,
    commitDetailLoading: false,
    diffLoading: false,
    fileContentLoading: false,
    statusError: null,
    treeError: null,
    fileContentError: null,
    sandboxContainers: [],
    sandboxContainersLoaded: false,
    sandboxContainer: null,
    sandboxRoot: null,
    sandboxDirCache: {},
    sandboxExpandedPaths: [],
    sandboxSelectedPath: null,
    sandboxContent: null,
    sandboxLoading: false,
    sandboxContentLoading: false,
    sandboxError: null,
    sandboxContentError: null,
    sandboxStarting: false,
  };
}

export const initialState: WorkspaceState = {
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

function touchLru(state: WorkspaceState, sessionId: string): void {
  const idx = state.lruOrder.indexOf(sessionId);
  if (idx !== -1) state.lruOrder.splice(idx, 1);
  state.lruOrder.push(sessionId);
  while (state.lruOrder.length > WORKSPACE_LRU_CAP) {
    const victim = state.lruOrder.shift();
    if (victim !== undefined) delete state.bySession[victim];
  }
}

export function ensureSlot(state: WorkspaceState, sessionId: string): SessionWorkspace {
  if (!state.bySession[sessionId]) {
    state.bySession[sessionId] = emptySessionWorkspace();
  }
  touchLru(state, sessionId);
  return state.bySession[sessionId];
}

export function writeToSlot(
  state: WorkspaceState,
  sessionId: string,
  mut: (slot: SessionWorkspace) => void,
): void {
  const slot = state.bySession[sessionId];
  if (!slot) return;
  mut(slot);
  touchLru(state, sessionId);
}

export function activeSlot(state: WorkspaceState): SessionWorkspace | null {
  const id = state.activeSessionId;
  return id ? state.bySession[id] ?? null : null;
}

// Clear the lazy tree, expansion, and open file when the browse target
// (container or root) changes, so stale paths from another root don't linger.
export function resetSandboxBrowse(slot: SessionWorkspace): void {
  slot.sandboxDirCache = {};
  slot.sandboxExpandedPaths = [];
  slot.sandboxSelectedPath = null;
  slot.sandboxContent = null;
  slot.sandboxContentError = null;
  slot.sandboxError = null;
  slot.sandboxStarting = false;
}
