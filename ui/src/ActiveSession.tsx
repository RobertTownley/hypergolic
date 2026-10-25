import { useEffect } from "react";
import { ZapIcon } from "lucide-react";
import { useAppDispatch, useAppSelector } from "@/store";
import { setActiveSession } from "@/store/sessionsSlice";
import { setLeftTab } from "@/store/uiSlice";
import {
  selectActiveSessionId,
  selectSessionsInitialized,
  selectProjectsInitialized,
  selectProjectIds,
  selectSessionIds,
  selectPendingApprovalForSession,
} from "@/store/selectors";
import { ChatView } from "@/chat/ChatView";
import { MergeReviewTakeover } from "@/review/MergeReviewTakeover";
import { EmptyState, Spinner } from "@/shared/components";

export function ActiveSession() {
  const dispatch = useAppDispatch();
  const activeSessionId = useAppSelector(selectActiveSessionId);
  const sessionsInitialized = useAppSelector(selectSessionsInitialized);
  const projectsInitialized = useAppSelector(selectProjectsInitialized);
  const projectIds = useAppSelector(selectProjectIds);
  const sessionIds = useAppSelector(selectSessionIds);
  const pendingApproval = useAppSelector((s) =>
    selectPendingApprovalForSession(s, activeSessionId ?? ""),
  );
  const reviewState = useAppSelector((s) => s.review.bySession[activeSessionId ?? ""]);

  useEffect(() => {
    if (!projectsInitialized || !sessionsInitialized) return;
    if (activeSessionId) return;

    if (projectIds.length === 0) {
      dispatch(setLeftTab("projects"));
      return;
    }

    if (sessionIds.length > 0) {
      dispatch(setActiveSession(sessionIds[0]));
    } else {
      dispatch(setLeftTab("projects"));
    }
  }, [projectsInitialized, sessionsInitialized, activeSessionId, projectIds, sessionIds, dispatch]);

  if (!projectsInitialized || !sessionsInitialized) {
    return <EmptyState><Spinner size="large" centered /></EmptyState>;
  }

  if (!activeSessionId) {
    return (
      <EmptyState
        icon={<ZapIcon style={{ fontSize: 48, color: "#2a2a3e" }} />}
        text="No active session"
      />
    );
  }

  const mergeApproval = pendingApproval?.toolId === "land" ? pendingApproval : null;
  const takeoverVisible = mergeApproval
    ? !reviewState?.dismissedToolUseIds[mergeApproval.toolUseId]
    : !!reviewState?.manuallyOpen;

  if (takeoverVisible) {
    return (
      <MergeReviewTakeover
        key={activeSessionId}
        sessionId={activeSessionId}
        approval={mergeApproval}
      />
    );
  }

  return <ChatView key={activeSessionId} sessionId={activeSessionId} />;
}
