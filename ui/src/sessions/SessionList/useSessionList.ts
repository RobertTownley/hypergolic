import { useCallback, useEffect, useState } from "react";
import { useSessions } from "@/hooks/useSession";
import { useActiveProject } from "@/hooks/useProject";
import { useAppSelector } from "@/store";
import { selectJumpToSessionId } from "@/store/selectors";
import { NEW_SESSION_EVENT, JUMP_TO_SESSION_EVENT, FOCUS_CHAT_EVENT } from "@/hooks/useKeyboardShortcuts";
import type { ModelTier, Session } from "@/types/api";

export function useSessionList() {
  const { projectId: activeProjectId } = useActiveProject();
  const {
    ids,
    entities,
    activeSessionId,
    getChildSessions,
    createSession,
    deleteSession,
    selectSession,
  } = useSessions();

  const clientMessageCount = useAppSelector(
    (s) => activeSessionId ? s.messages.bySessionId[activeSessionId]?.length ?? 0 : 0,
  );
  const serverMessageCount = activeSessionId ? entities[activeSessionId]?.message_count ?? 0 : 0;
  const activeMessageCount = Math.max(serverMessageCount, clientMessageCount);

  const [showModal, setShowModal] = useState(false);
  const [pulseSessionId, setPulseSessionId] = useState<string | null>(null);

  const triggerNewSession = useCallback(() => {
    if (!activeProjectId) return;
    setShowModal(true);
  }, [activeProjectId]);

  useEffect(() => {
    const open = () => triggerNewSession();
    window.addEventListener(NEW_SESSION_EVENT, open);
    return () => window.removeEventListener(NEW_SESSION_EVENT, open);
  }, [triggerNewSession]);

  const jumpToSessionId = useAppSelector(selectJumpToSessionId);

  useEffect(() => {
    const jump = () => {
      if (jumpToSessionId) {
        selectSession(jumpToSessionId);
        window.dispatchEvent(new Event(FOCUS_CHAT_EVENT));
      }
    };
    window.addEventListener(JUMP_TO_SESSION_EVENT, jump);
    return () => window.removeEventListener(JUMP_TO_SESSION_EVENT, jump);
  }, [jumpToSessionId, selectSession]);

  const handleNewSession = async (
    projectId: string,
    baseBranch: string,
    modelTier: ModelTier,
    role: string,
  ) => {
    if (activeSessionId && activeMessageCount === 0) {
      const active = entities[activeSessionId];
      if (
        active &&
        active.project_id === projectId &&
        active.model_tier === modelTier &&
        active.role === role &&
        (active.base_branch ?? null) === baseBranch
      ) {
        setShowModal(false);
        setPulseSessionId(activeSessionId);
        setTimeout(() => setPulseSessionId(null), 600);
        return;
      }
    }
    setShowModal(false);
    await createSession(projectId, baseBranch, modelTier, role);
  };

  const handleSelectSession = (id: string) => {
    selectSession(id);
  };

  const handleDeleteSession = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    deleteSession(id);
  };

  return {
    ids,
    entities: entities as Record<string, Session>,
    activeSessionId,
    getChildSessions,
    showModal,
    setShowModal,
    pulseSessionId,
    activeProjectId,
    triggerNewSession,
    handleNewSession,
    handleSelectSession,
    handleDeleteSession,
  };
}
