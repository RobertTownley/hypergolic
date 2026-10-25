import { useEffect, useCallback } from "react";
import { useAppSelector, useAppDispatch } from "@/store";
import { loadSessionContext } from "@/store/sessionsSlice";
import { useSessionMessages, useSendMessage } from "@/hooks/useMessages";
import { useLedgerScroll } from "@/chat/Ledger";
import type { ModelTier, ContentBlock, Annotation } from "@/types/api";

export function useChatView(sessionId: string) {
  const dispatch = useAppDispatch();
  const {
    messages,
    loading: loadingMessages,
    streaming,
    pendingApproval,
    error,
  } = useSessionMessages(sessionId);

  const { sendMessage, sendApprovalResponse } = useSendMessage(sessionId);

  const sessionStatus = useAppSelector((s) => s.sessions.entities[sessionId]?.status);
  const isTruncating = sessionStatus === "truncating";
  const isRetrying = sessionStatus === "retrying";

  const { viewportRef, contentRef, showJumpToLatest, scrollToBottom } = useLedgerScroll(messages.length);

  useEffect(() => {
    dispatch(loadSessionContext(sessionId));
  }, [sessionId, dispatch]);

  const handleSend = useCallback(
    async (message: string, modelTier: ModelTier, contentBlocks?: ContentBlock[], workflowId?: string) => {
      scrollToBottom();
      await sendMessage(message, modelTier, contentBlocks, workflowId);
    },
    [sendMessage, scrollToBottom],
  );

  const handleApprovalResponse = useCallback(
    async (sessionId: string, toolUseId: string, approved: boolean, denialReason?: string, annotations?: Annotation[]) => {
      await sendApprovalResponse(sessionId, toolUseId, approved, denialReason, annotations);
    },
    [sendApprovalResponse],
  );

  return {
    messageCount: messages.length,
    loadingMessages,
    streaming,
    error,
    pendingApproval,
    isTruncating,
    isRetrying,
    sessionStatus,
    viewportRef,
    contentRef,
    showJumpToLatest,
    scrollToBottom,
    handleSend,
    sendApprovalResponse: handleApprovalResponse,
  };
}
