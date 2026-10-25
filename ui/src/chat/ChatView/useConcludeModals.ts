import { useState, useEffect, useCallback } from "react";
import { useWebSocket } from "@/api/WebSocketProvider";
import { useAppDispatch, useAppSelector } from "@/store";
import { clearConcludeError, selectConcludeError } from "@/store/sessionsSlice";
import { CONCLUDE_SESSION_EVENT, EXPORT_SESSION_EVENT } from "@/hooks/useKeyboardShortcuts";
import type { SessionStatus } from "@/types/api";

export function useConcludeModals(sessionId: string, sessionStatus: SessionStatus | undefined) {
  const ws = useWebSocket();
  const dispatch = useAppDispatch();
  const [showConcludeModal, setShowConcludeModal] = useState(false);
  const [showExportModal, setShowExportModal] = useState(false);
  const concludeError = useAppSelector((s) => selectConcludeError(s, sessionId));

  useEffect(() => {
    const handle = () => setShowExportModal(true);
    window.addEventListener(EXPORT_SESSION_EVENT, handle);
    return () => window.removeEventListener(EXPORT_SESSION_EVENT, handle);
  }, []);

  useEffect(() => {
    const handleConcludeEvent = () => {
      if (sessionStatus !== "concluding" && sessionStatus !== "concluded" && sessionStatus !== "interrupted") {
        setShowConcludeModal(true);
      }
    };
    window.addEventListener(CONCLUDE_SESSION_EVENT, handleConcludeEvent);
    return () => window.removeEventListener(CONCLUDE_SESSION_EVENT, handleConcludeEvent);
  }, [sessionStatus]);

  const concludeModalOpen = showConcludeModal || concludeError !== null;

  const handleConclude = useCallback(
    async (
      rating: number,
      feedback: string,
      deleteWorktree: boolean,
      deleteBranch: boolean,
      analyzeLearnings: boolean,
    ) => {
      setShowConcludeModal(false);
      dispatch(clearConcludeError(sessionId));

      await ws.sendRaw({
        type: "conclude_session",
        session_id: sessionId,
        rating,
        feedback: feedback || null,
        delete_worktree: deleteWorktree,
        delete_branch: deleteBranch,
        analyze_learnings: analyzeLearnings,
      });
    },
    [sessionId, ws, dispatch],
  );

  const closeConcludeModal = useCallback(() => {
    setShowConcludeModal(false);
    dispatch(clearConcludeError(sessionId));
  }, [sessionId, dispatch]);

  return {
    showConcludeModal: concludeModalOpen,
    concludeError,
    showExportModal,
    closeConcludeModal,
    closeExportModal: () => setShowExportModal(false),
    handleConclude,
  };
}
