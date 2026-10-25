import { useCallback, useEffect, useMemo, useState } from "react";
import { useAppDispatch, useAppSelector } from "@/store";
import type { AppDispatch } from "@/store";
import {
  selectActiveSessionId,
  selectActiveWorkspace,
  selectActionOutput,
  selectGitError,
  selectDiffMode,
  selectRepoScope,
  selectAvailableRepos,
} from "@/store/selectors";
import { clearActionOutput, setDiffMode, setRepoScope } from "@/store/workspaceSlice";
import { loadGitStatus, loadGitLog, loadBranches, checkoutBranch, createBranch, loadFileTree, loadRepos, loadChanges } from "@/store/workspaceThunks";
import { useFileWatcher } from "@/hooks/useFileWatcher";
import { buildTree, useExpandedDirs } from "@/git/FileTree";
import type { FileTreeNode } from "@/git/FileTree";
import type { GitStatusResponse, DiffMode, RepoScope } from "@/types/api";

export interface VersionControlState {
  status: GitStatusResponse | null;
  loading: boolean;
  actionOutput: string | null;
  error: string | null;
  expandedDirs: Set<string>;
  toggleDir: (path: string) => void;
  refresh: () => void;
  stagedTree: FileTreeNode | null;
  unstagedTree: FileTreeNode | null;
  allChangesTree: FileTreeNode | null;
  hasStagedFiles: boolean;
  hasUnstagedFiles: boolean;
  hasUntracked: boolean;
  hasUncommittedChanges: boolean;
  hasAllChanges: boolean;
  diffMode: DiffMode;
  onSetDiffMode: (mode: DiffMode) => void;
  repoScope: RepoScope;
  onSetRepoScope: (scope: RepoScope) => void;
  availableRepos: Record<RepoScope, boolean> | null;
  branches: string[];
  checkoutLoading: boolean;
  handleCheckout: (branch: string) => void;
  handleCreateBranch: (name: string) => void;
  dispatch: AppDispatch;
}

export function useVersionControl(): VersionControlState {
  const dispatch = useAppDispatch();
  const { status, loading, branches, statusError } = useAppSelector(selectActiveWorkspace);
  const actionOutput = useAppSelector(selectActionOutput);
  const error = useAppSelector(selectGitError);
  const diffMode = useAppSelector(selectDiffMode);
  const repoScope = useAppSelector(selectRepoScope);
  const availableRepos = useAppSelector(selectAvailableRepos);
  const activeSessionId = useAppSelector(selectActiveSessionId);
  const [checkoutLoading, setCheckoutLoading] = useState(false);

  const refresh = useCallback(() => {
    if (!activeSessionId) return;
    dispatch(loadGitStatus({ sessionId: activeSessionId }));
    dispatch(loadGitLog({ sessionId: activeSessionId, count: 50 }));
    dispatch(loadChanges({ sessionId: activeSessionId, mode: diffMode, force: true }));
    dispatch(loadBranches({ sessionId: activeSessionId }));
    dispatch(loadFileTree({ sessionId: activeSessionId }));
    // A /harness or /shared repo can materialize after mount (sandbox still
    // starting); refresh re-checks so the toggle un-disables.
    dispatch(loadRepos({ sessionId: activeSessionId }));
  }, [dispatch, activeSessionId, diffMode]);

  const autoRefresh = useMemo(
    () => () => { if (activeSessionId) dispatch(loadGitStatus({ sessionId: activeSessionId })); },
    [dispatch, activeSessionId],
  );

  useFileWatcher(autoRefresh);

  useEffect(() => {
    if (activeSessionId) dispatch(loadRepos({ sessionId: activeSessionId }));
  }, [dispatch, activeSessionId]);

  useEffect(() => {
    if (actionOutput) {
      const t = setTimeout(() => dispatch(clearActionOutput()), 5000);
      return () => clearTimeout(t);
    }
  }, [actionOutput, dispatch]);

  const { stagedTree, unstagedTree, allChangesTree } = useMemo(() => {
    if (!status) return { stagedTree: null, unstagedTree: null, allChangesTree: null };
    return {
      stagedTree: buildTree(status.staged, []),
      unstagedTree: buildTree(status.unstaged, status.untracked),
      allChangesTree: buildTree(status.all_changes ?? [], []),
    };
  }, [status]);

  const trees = useMemo(
    () => [stagedTree, unstagedTree, allChangesTree],
    [stagedTree, unstagedTree, allChangesTree],
  );
  const { expandedDirs, toggleDir } = useExpandedDirs(trees);

  const handleCheckout = useCallback(async (branch: string) => {
    if (!activeSessionId) return;
    setCheckoutLoading(true);
    try {
      await dispatch(checkoutBranch({ sessionId: activeSessionId, branch }));
    } finally {
      setCheckoutLoading(false);
    }
  }, [dispatch, activeSessionId]);

  const onSetDiffMode = useCallback((mode: DiffMode) => {
    if (mode === diffMode) return;
    dispatch(setDiffMode(mode));
    if (activeSessionId) dispatch(loadGitStatus({ sessionId: activeSessionId }));
  }, [dispatch, diffMode, activeSessionId]);

  const onSetRepoScope = useCallback((scope: RepoScope) => {
    if (scope === repoScope) return;
    dispatch(setRepoScope(scope));
    if (activeSessionId) {
      // force: an in-flight fetch for the previous repo must not swallow
      // the refetch for this one.
      dispatch(loadGitStatus({ sessionId: activeSessionId, force: true }));
      dispatch(loadGitLog({ sessionId: activeSessionId, count: 50, force: true }));
    }
  }, [dispatch, repoScope, activeSessionId]);

  const handleCreateBranch = useCallback(async (name: string) => {
    if (!activeSessionId) return;
    setCheckoutLoading(true);
    try {
      await dispatch(createBranch({ sessionId: activeSessionId, name }));
    } finally {
      setCheckoutLoading(false);
    }
  }, [dispatch, activeSessionId]);

  const hasStagedFiles = (status?.staged.length ?? 0) > 0;
  const hasUnstagedFiles = (status?.unstaged.length ?? 0) > 0;
  const hasUntracked = (status?.untracked.length ?? 0) > 0;
  const hasAllChanges = (status?.all_changes?.length ?? 0) > 0;
  const hasUncommittedChanges = hasStagedFiles || hasUnstagedFiles || hasUntracked;

  return {
    status, loading, actionOutput,
    error: error ?? statusError,
    expandedDirs, toggleDir, refresh,
    stagedTree, unstagedTree, allChangesTree,
    hasStagedFiles, hasUnstagedFiles, hasUntracked,
    hasUncommittedChanges, hasAllChanges,
    diffMode, onSetDiffMode,
    repoScope, onSetRepoScope, availableRepos,
    branches, checkoutLoading, handleCheckout, handleCreateBranch, dispatch,
  };
}
