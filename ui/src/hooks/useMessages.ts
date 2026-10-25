import { useCallback, useEffect } from "react";
import { useAppDispatch, useAppSelector } from "@/store";
import {
  selectMessagesForSession,
  selectIsSessionStreaming,
  selectPendingApprovalForSession,
  selectSessionError,
  selectIsMessagesLoading,
  selectIsMessagesLoaded,
} from "@/store/selectors";
import {
  loadMessages,
  setSessionStreaming,
  setSessionError,
  addUserMessage,
  clearAllPendingApprovals,
} from "@/store/messagesSlice";
import { useWebSocket } from "@/api/WebSocketProvider";
import type { ModelTier, ContentBlock } from "@/types/api";

/**
 * Hook for accessing messages for a specific session.
 * Automatically loads messages when the session changes.
 */
export function useSessionMessages(sessionId: string | null) {
  const dispatch = useAppDispatch();

  // Use empty defaults when no sessionId
  const messages = useAppSelector((state) =>
    sessionId ? selectMessagesForSession(state, sessionId) : []
  );
  const loading = useAppSelector((state) =>
    sessionId ? selectIsMessagesLoading(state, sessionId) : false
  );
  const loaded = useAppSelector((state) =>
    sessionId ? selectIsMessagesLoaded(state, sessionId) : false
  );
  // Deliberately no subscription to streaming *blocks* here: they change on
  // every streamed token, and this hook backs ChatView. StreamingSection is
  // the one component that subscribes to them.
  const streaming = useAppSelector((state) =>
    sessionId ? selectIsSessionStreaming(state, sessionId) : false
  );
  const pendingApproval = useAppSelector((state) =>
    sessionId ? selectPendingApprovalForSession(state, sessionId) : null
  );
  const error = useAppSelector((state) =>
    sessionId ? selectSessionError(state, sessionId) : null
  );

  const refresh = useCallback(() => {
    if (sessionId) {
      dispatch(loadMessages(sessionId));
    }
  }, [dispatch, sessionId]);

  // Load messages when sessionId changes and not already loaded
  useEffect(() => {
    if (sessionId && !loaded && !loading) {
      dispatch(loadMessages(sessionId));
    }
  }, [dispatch, sessionId, loaded, loading]);

  return {
    messages,
    loading,
    loaded,
    streaming,
    pendingApproval,
    error,
    refresh,
  };
}

/**
 * Hook for sending messages in a session
 */
export function useSendMessage(sessionId: string | null) {
  const dispatch = useAppDispatch();
  const { send, sendApprovalResponse } = useWebSocket();

  const sendMessage = useCallback(
    async (message: string, modelTier: ModelTier, contentBlocks?: ContentBlock[], workflowId?: string) => {
      if (!sessionId) return;

      dispatch(setSessionError({ sessionId, error: null }));
      dispatch(addUserMessage({ sessionId, text: message, contentBlocks }));
      dispatch(setSessionStreaming({ sessionId, streaming: true }));

      try {
        await send(message, sessionId, modelTier, contentBlocks, workflowId);
      } catch {
        dispatch(setSessionError({ sessionId, error: "Failed to connect to server" }));
        dispatch(setSessionStreaming({ sessionId, streaming: false }));
      }
    },
    [sessionId, dispatch, send],
  );

  const approveToolUse = useCallback(
    async (toolUseId: string) => {
      if (!sessionId) return;
      await sendApprovalResponse(sessionId, toolUseId, true);
    },
    [sessionId, sendApprovalResponse],
  );

  const denyToolUse = useCallback(
    async (toolUseId: string, reason?: string) => {
      if (!sessionId) return;
      await sendApprovalResponse(sessionId, toolUseId, false, reason);
    },
    [sessionId, sendApprovalResponse],
  );

  const clearApproval = useCallback(() => {
    if (!sessionId) return;
    dispatch(clearAllPendingApprovals(sessionId));
  }, [dispatch, sessionId]);

  return {
    sendMessage,
    approveToolUse,
    denyToolUse,
    clearApproval,
    sendApprovalResponse,
  };
}

/**
 * Hook for accessing messages for the active session.
 * This is a convenience wrapper around useSessionMessages.
 */

