import type { AppDispatch } from "@/store";
import { store } from "@/store";
import {
  setSessionStreaming,
  setSessionError,
  clearStreamingContent,
  loadMessages,
  clearAllPendingApprovals,
} from "@/store/messagesSlice";
import { loadSessions, loadSessionContext, upsertSession, concludeSession, setActiveSession, updateSessionStatus } from "@/store/sessionsSlice";
import { upsertGitStatus } from "@/store/workspaceSlice";
import { rankJumpCandidates } from "@/store/selectors";
import { loadGitStatus, loadGitLog, loadChanges } from "@/store/workspaceThunks";
import type { WsDone, WsInterrupted, WsError, WsDispatchStarted, WsSessionConcluded, WsSessionStatusChange, WsSandboxStatusChange, Session, SessionStatus } from "@/types/api";

const TURN_ACTIVE_STATUSES: ReadonlySet<SessionStatus> = new Set<SessionStatus>([
  "thinking", "streaming", "retrying", "tool_use", "truncating", "awaiting_approval",
]);

/**
 * Status broadcasts are the only signal for a turn this client didn't start —
 * one resumed after a server restart, or one driven by a dispatching parent.
 * Without this the session streams invisibly: no activity indicator, and the
 * next thing the user types cancels a turn they never saw running.
 */
export function handleSessionStatusChange(dispatch: AppDispatch, event: WsSessionStatusChange): void {
  const status = event.content[0]?.status;
  if (!status) return;
  dispatch(updateSessionStatus({
    sessionId: event.session_id, status,
    concludedAt: event.content[0]?.concluded_at,
  }));
  if (TURN_ACTIVE_STATUSES.has(status)) {
    dispatch(setSessionStreaming({ sessionId: event.session_id, streaming: true }));
  } else if (status === "idle") {
    dispatch(setSessionStreaming({ sessionId: event.session_id, streaming: false }));
  }
}

// Sandbox coming up is the retry signal for git panels that errored while it
// was down (git state lives in-container); only cached workspaces refetch.
export function handleSandboxStatusChange(dispatch: AppDispatch, event: WsSandboxStatusChange): void {
  if (event.content[0]?.status !== "running") return;
  const sessionId = event.session_id;
  const workspace = store.getState().workspace;
  if (!workspace.bySession[sessionId]) return;
  dispatch(loadGitStatus({ sessionId, force: true }));
  dispatch(loadGitLog({ sessionId, force: true }));
  dispatch(loadChanges({ sessionId, mode: workspace.diffMode, force: true }));
}

export function handleDone(dispatch: AppDispatch, event: WsDone): void {
  dispatch(clearStreamingContent(event.session_id));
  dispatch(setSessionStreaming({ sessionId: event.session_id, streaming: false }));
  dispatch(clearAllPendingApprovals(event.session_id));
  if (event.git_status) {
    // Session-addressed write: the slot for event.session_id is updated
    // regardless of whether it's the active session, so a background
    // session that finishes streaming has its cached status refreshed
    // too. writeToSlot no-ops if the slot was evicted.
    dispatch(upsertGitStatus({ sessionId: event.session_id, status: event.git_status }));
  }
  const workspace = store.getState().workspace;
  if (workspace.bySession[event.session_id]) {
    dispatch(loadChanges({ sessionId: event.session_id, mode: workspace.diffMode, force: true }));
  }
  dispatch(loadSessionContext(event.session_id));
}

export function handleInterrupted(dispatch: AppDispatch, event: WsInterrupted): void {
  if (!event.session_id) return;
  dispatch(clearStreamingContent(event.session_id));
  dispatch(setSessionStreaming({ sessionId: event.session_id, streaming: false }));
  dispatch(loadMessages(event.session_id));
  dispatch(clearAllPendingApprovals(event.session_id));
}

export function handleError(dispatch: AppDispatch, event: WsError): void {
  if (!event.session_id) return;
  dispatch(clearStreamingContent(event.session_id));
  dispatch(setSessionError({ sessionId: event.session_id, error: event.detail }));
  dispatch(setSessionStreaming({ sessionId: event.session_id, streaming: false }));
  dispatch(loadMessages(event.session_id));
  dispatch(clearAllPendingApprovals(event.session_id));
}

export function handleDispatchStarted(dispatch: AppDispatch, event: WsDispatchStarted): void {
  const childData = event.content[0];
  if (childData?.child_session) {
    dispatch(upsertSession(childData.child_session));
  } else if (childData?.child_session_id) {
    dispatch(loadSessions());
  }
}

export function handleSessionConcluded(dispatch: AppDispatch, event: WsSessionConcluded): void {
  dispatch(concludeSession({
    sessionId: event.session_id,
    rating: event.conclusion_rating,
    feedback: event.conclusion_feedback,
    concludedAt: event.concluded_at,
  }));
  // Auto-navigate away from the now-concluded session. Only fires after
  // the server confirms the conclude succeeded, so dirty-worktree
  // rejections leave the user on the current session where the modal
  // can re-open with the error.
  const state = store.getState();
  if (state.sessions.activeSessionId !== event.session_id) return;
  const candidates = state.sessions.ids
    .map((id: string) => state.sessions.entities[id])
    // Never land on the concluded session's own children — notably the
    // post-conclude distillation child, which is busy but not the user's.
    .filter((s): s is Session => !!s && s.id !== event.session_id && s.parent_id !== event.session_id);
  const next = rankJumpCandidates(candidates)[0];
  if (next) {
    dispatch(setActiveSession(next.id));
  }
}
