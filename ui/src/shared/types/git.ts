export interface FileNode {
  name: string;
  path: string;
  is_dir: boolean;
  git_status: string | null;
  children: FileNode[] | null;
}

// Scoped workspace responses carry the session_id the backend used so
// the reducer can route late-arriving responses back to the right
// per-session slot in workspaceSlice.bySession.
export interface FileTreeResponse {
  session_id: string;
  root: string;
  tree: FileNode[];
}

export interface FileContentResponse {
  session_id: string;
  path: string;
  content: string;
  language: string;
}

export interface ChangedFile {
  path: string;
  status: string;
  staged: boolean;
  additions: number;
  deletions: number;
}

export interface GitStatusResponse {
  session_id: string;
  branch: string;
  ahead: number;
  behind: number;
  staged: ChangedFile[];
  unstaged: ChangedFile[];
  untracked: string[];
  all_changes: ChangedFile[];
}

// "all": everything between the worktree branch and its base branch
// (committed + uncommitted). "uncommitted": only working-tree changes.
export type DiffMode = "all" | "uncommitted";

// Which of the sandbox's host-backed repos the Source Control panel shows:
// the project worktree (/app), the session's harness worktree (/harness),
// or the project's persistent shared repo (/shared).
export type RepoScope = "app" | "harness" | "shared";

export interface GitReposResponse {
  session_id: string;
  repos: Record<RepoScope, boolean>;
}

export interface GitDiffResponse {
  session_id: string;
  path: string;
  diff: string;
}

export interface GitLogEntry {
  hash: string;
  short_hash: string;
  author: string;
  date: string;
  message: string;
  refs: string;
}

export interface GitReviewFile {
  path: string;
  old_path: string | null;
  status: string;
  additions: number;
  deletions: number;
  patch: string;
}

export interface MergeCandidate {
  parents: string[];
  merged_from: string;
  merged_count: number;
  conflict_paths: string[];
  view: "merge" | "range";
}

export interface GitReviewResponse {
  session_id: string;
  branch: string;
  base_branch: string;
  merge_base: string;
  ahead: number;
  behind: number;
  commits: GitLogEntry[];
  files: GitReviewFile[];
  merge?: MergeCandidate | null;
}

export interface GitChangesResponse {
  session_id: string;
  files: GitReviewFile[];
}

export interface GitLogResponse {
  session_id: string;
  entries: GitLogEntry[];
}

export interface GitCommitDetail {
  session_id: string;
  hash: string;
  short_hash: string;
  author: string;
  date: string;
  message: string;
  diff: string;
}

export interface GitBranchesResponse {
  session_id: string;
  branches: string[];
  current: string;
}
