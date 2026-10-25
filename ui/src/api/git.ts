import type {
  GitStatusResponse,
  GitDiffResponse,
  GitLogResponse,
  GitReviewResponse,
  GitChangesResponse,
  GitCommitDetail,
  GitBranchesResponse,
  DiffMode,
  RepoScope,
  GitReposResponse,
} from "@/types/api";
import { getJson, request, jsonBody } from "@/api/http";

const BASE = "/api";

// The only scope
// primitive passed to workspace endpoints is the session id. The backend
// resolves the on-disk repo from the session row (falling back to the
// session's project if the worktree isn't ready). ``sessionId`` is
// required — calling these APIs without a focused session is a bug in
// the caller, not a case we silently swallow.
export interface SessionScope {
  sessionId: string;
  // Which sandbox repo the request addresses; omitted means "app".
  repoScope?: RepoScope;
}

function scopeQuery(scope: SessionScope): string {
  const repo = scope.repoScope ? `&repo_scope=${scope.repoScope}` : "";
  return `?session_id=${encodeURIComponent(scope.sessionId)}${repo}`;
}

export async function fetchGitRepos(scope: SessionScope): Promise<GitReposResponse> {
  return getJson(`${BASE}/git/repos${scopeQuery(scope)}`, "Failed to fetch available repos");
}

export async function fetchGitStatus(scope: SessionScope, mode: DiffMode = "all"): Promise<GitStatusResponse> {
  return getJson(`${BASE}/git/status${scopeQuery(scope)}&mode=${mode}`, "Failed to fetch git status");
}

export async function fetchGitDiff(path: string, staged: boolean, scope: SessionScope, base = false): Promise<GitDiffResponse> {
  return getJson(`${BASE}/git/diff${scopeQuery(scope)}`, "Failed to fetch diff", jsonBody({ path, staged, base }));
}

export async function gitStageFiles(paths: string[], scope: SessionScope): Promise<void> {
  await request(`${BASE}/git/stage${scopeQuery(scope)}`, "Failed to stage files", jsonBody({ paths }));
}

export async function gitUnstageFiles(paths: string[], scope: SessionScope): Promise<void> {
  await request(`${BASE}/git/unstage${scopeQuery(scope)}`, "Failed to unstage files", jsonBody({ paths }));
}

export async function gitDiscardFiles(paths: string[], scope: SessionScope): Promise<void> {
  await request(`${BASE}/git/discard${scopeQuery(scope)}`, "Failed to discard changes", jsonBody({ paths }));
}

export type ReviewView = "merge" | "range";

export interface CandidateSpan {
  head: string;
  base: string;
  branch?: string;
  view?: ReviewView;
}

export async function fetchGitReview(
  scope: SessionScope,
  span?: CandidateSpan,
): Promise<GitReviewResponse> {
  const branchQuery = span?.branch ? `&branch=${encodeURIComponent(span.branch)}` : "";
  const viewQuery = span?.view ? `&view=${span.view}` : "";
  const spanQuery = span ? `&head=${span.head}&base=${span.base}${branchQuery}${viewQuery}` : "";
  return getJson(`${BASE}/git/review${scopeQuery(scope)}${spanQuery}`, "Failed to fetch review");
}

export async function fetchGitChanges(mode: DiffMode, scope: SessionScope): Promise<GitChangesResponse> {
  return getJson(`${BASE}/git/changes${scopeQuery(scope)}&mode=${mode}`, "Failed to fetch changes");
}

export async function fetchGitLog(count: number, scope: SessionScope): Promise<GitLogResponse> {
  return getJson(`${BASE}/git/log${scopeQuery(scope)}&count=${count}`, "Failed to fetch git log");
}

export async function fetchGitCommitDetail(hash: string, scope: SessionScope): Promise<GitCommitDetail> {
  return getJson(`${BASE}/git/show/${hash}${scopeQuery(scope)}`, "Failed to fetch commit detail");
}

export async function fetchGitBranches(scope: SessionScope): Promise<GitBranchesResponse> {
  return getJson(`${BASE}/git/branches${scopeQuery(scope)}`, "Failed to fetch branches");
}

export async function gitCreateBranch(name: string, scope: SessionScope): Promise<GitStatusResponse> {
  return getJson(`${BASE}/git/branch${scopeQuery(scope)}`, "Failed to create branch", jsonBody({ name }));
}

export async function gitCheckout(branch: string, scope: SessionScope): Promise<GitStatusResponse> {
  return getJson(`${BASE}/git/checkout${scopeQuery(scope)}`, "Failed to checkout branch", jsonBody({ branch }));
}
