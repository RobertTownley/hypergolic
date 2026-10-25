import { useCallback, useEffect, useMemo, useState } from "react";
import { useAppDispatch, useAppSelector } from "@/store";
import type { PendingApproval } from "@/store/messagesSlice";
import { useWebSocket } from "@/api/WebSocketProvider";
import { buildTree, orderedFilePaths, useExpandedDirs } from "@/git/FileTree";
import type { RepoScope } from "@/types/api";
import {
  addComment,
  closeReview,
  loadGitReview,
  removeComment,
  selectReviewFile,
  setDiffMode,
  setOverallNote,
  toggleViewed,
  clearReviewState,
  type DiffMode,
  type ReviewComment,
} from "@/store/reviewSlice";
import { useReviewDenial } from "@/review/useReviewDenial";
import type { ReviewView } from "@/api/git";

export function useMergeReview(sessionId: string, approval: PendingApproval | null) {
  const dispatch = useAppDispatch();
  const { sendApprovalResponse } = useWebSocket();
  const denial = useReviewDenial(sessionId);

  const reviewState = useAppSelector((s) => s.review.bySession[sessionId]);
  const viewed = reviewState?.viewed ?? {};
  const comments = useMemo(() => reviewState?.comments ?? [], [reviewState?.comments]);
  const diffMode: DiffMode = reviewState?.diffMode ?? "unified";
  const overallNote = reviewState?.overallNote ?? "";
  const review = reviewState?.review.data ?? null;
  const error = reviewState?.review.error ?? null;
  // Loading until the first fetch settles, and during any refetch. The slot
  // may exist (comments, viewed, …) before the review has ever been fetched.
  const loading = (reviewState?.review.loading ?? false) || (!review && !error);

  const toolUseId = approval?.toolUseId;
  // A pending land approval reviews whichever repo was pushed: the /harness
  // or /shared clone, or the project workspace.
  const repo = approval?.toolInput?.repo;
  const repoScope: RepoScope = repo === "harness" || repo === "shared" ? repo : "app";
  // A land approval reviews the exact host-side candidate span that would
  // land — never the workspace, whose state the gate does not trust.
  const args = approval?.toolInput?.arguments as
    | { sha?: string; base_sha?: string; branch?: string }
    | undefined;
  const head = args?.sha;
  const base = args?.base_sha;
  const branch = args?.branch;
  // A merge-commit candidate opens on its own contribution (conflict
  // resolutions); "range" widens to everything the merge brought in.
  const [view, setView] = useState<ReviewView>("merge");

  // Refetch when the session or the pending approval changes. Concurrent
  // dispatches (e.g. two panels mounted alongside) dedupe to one
  // request via the dedupeThunk middleware.
  useEffect(() => {
    const span = head && base ? { head, base, branch, view } : undefined;
    dispatch(loadGitReview({ sessionId, repoScope, span }));
  }, [dispatch, sessionId, toolUseId, repoScope, head, base, branch, view]);

  const files = useMemo(() => review?.files ?? [], [review]);
  const fileTree = useMemo(() => buildTree(files, []), [files]);
  const trees = useMemo(() => [fileTree], [fileTree]);
  const { expandedDirs, toggleDir } = useExpandedDirs(trees);
  const orderedPaths = useMemo(() => orderedFilePaths(fileTree), [fileTree]);
  const storedPath = reviewState?.selectedPath ?? null;
  const selectedPath =
    storedPath && files.some((f) => f.path === storedPath)
      ? storedPath
      : orderedPaths[0] ?? null;
  const selectedFile = files.find((f) => f.path === selectedPath) ?? null;

  const viewedCount = files.filter((f) => viewed[f.path]).length;

  const selectFile = useCallback(
    (path: string | null) => dispatch(selectReviewFile({ sessionId, path })),
    [dispatch, sessionId],
  );

  const stepFile = useCallback(
    (delta: number) => {
      if (orderedPaths.length === 0) return;
      const idx = orderedPaths.indexOf(selectedPath ?? "");
      const next = Math.min(orderedPaths.length - 1, Math.max(0, idx + delta));
      dispatch(selectReviewFile({ sessionId, path: orderedPaths[next] }));
    },
    [dispatch, sessionId, orderedPaths, selectedPath],
  );

  const handleToggleViewed = useCallback(
    (path: string) => dispatch(toggleViewed({ sessionId, path })),
    [dispatch, sessionId],
  );

  const handleSetDiffMode = useCallback(
    (mode: DiffMode) => dispatch(setDiffMode({ sessionId, mode })),
    [dispatch, sessionId],
  );

  const handleAddComment = useCallback(
    (comment: Omit<ReviewComment, "id">) =>
      dispatch(addComment({ sessionId, comment: { ...comment, id: crypto.randomUUID() } })),
    [dispatch, sessionId],
  );

  const handleRemoveComment = useCallback(
    (commentId: string) => dispatch(removeComment({ sessionId, commentId })),
    [dispatch, sessionId],
  );

  const handleSetOverallNote = useCallback(
    (note: string) => dispatch(setOverallNote({ sessionId, note })),
    [dispatch, sessionId],
  );

  const handleClose = useCallback(
    () => dispatch(closeReview({ sessionId, toolUseId })),
    [dispatch, sessionId, toolUseId],
  );

  const handleApprove = useCallback(async () => {
    if (!toolUseId) return;
    await sendApprovalResponse(sessionId, toolUseId, true, undefined, denial.annotations);
    dispatch(clearReviewState({ sessionId }));
  }, [sendApprovalResponse, sessionId, toolUseId, denial, dispatch]);

  const handleRequestChanges = useCallback(async () => {
    if (!toolUseId) return;
    await sendApprovalResponse(
      sessionId, toolUseId, false, denial.reason(), denial.annotations,
    );
    dispatch(clearReviewState({ sessionId }));
  }, [sendApprovalResponse, sessionId, toolUseId, denial, dispatch]);

  return {
    review,
    view,
    setView,
    repoScope,
    loading,
    error,
    files,
    fileTree,
    expandedDirs,
    toggleDir,
    selectedPath,
    selectedFile,
    viewed,
    viewedCount,
    comments,
    diffMode,
    overallNote,
    setOverallNote: handleSetOverallNote,
    selectFile,
    stepFile,
    handleToggleViewed,
    handleSetDiffMode,
    handleAddComment,
    handleRemoveComment,
    handleClose,
    handleApprove,
    handleRequestChanges,
  };
}
