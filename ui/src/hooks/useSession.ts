import { useCallback, useMemo } from "react";
import { useAppDispatch, useAppSelector } from "@/store";
import {
  selectActiveSessionId,
  selectSessionEntities,
  selectSessionIds,
  selectSessionsInitialized,
  selectSessionsLoading,
} from "@/store/selectors";
import {
  setActiveSession,
  addSession,
  removeSession,
  loadSessions,
} from "@/store/sessionsSlice";
import { setLeftTab } from "@/store/uiSlice";
import type { ModelTier, Session } from "@/types/api";

/**
 * Hook for accessing and managing the active session
 */

/**
 * Hook for accessing a specific session by ID
 */

/**
 * Hook for session list operations
 */
export function useSessions() {
  const dispatch = useAppDispatch();
  const ids = useAppSelector(selectSessionIds);
  const entities = useAppSelector(selectSessionEntities);
  const activeSessionId = useAppSelector(selectActiveSessionId);
  const initialized = useAppSelector(selectSessionsInitialized);
  const loading = useAppSelector(selectSessionsLoading);

  const sessions = useMemo(
    () => ids.map((id: string) => entities[id]).filter((s): s is Session => !!s),
    [ids, entities],
  );

  const rootSessions = useMemo(
    () => sessions.filter((s: Session) => !s.parent_id),
    [sessions],
  );

  const getChildSessions = useCallback(
    (parentId: string) => sessions.filter((s: Session) => s.parent_id === parentId),
    [sessions],
  );

  const createSession = useCallback(
    async (
      projectId: string,
      baseBranch: string,
      modelTier: ModelTier = "High",
      role: string = "generalist",
    ) => {
      const result = await dispatch(
        addSession({ projectId, baseBranch, modelTier, role }),
      );
      if (addSession.fulfilled.match(result)) {
        dispatch(setActiveSession(result.payload.id));
        return result.payload;
      }
      return null;
    },
    [dispatch],
  );

  const deleteSession = useCallback(
    (sessionId: string) => {
      dispatch(removeSession(sessionId));
    },
    [dispatch],
  );

  const selectSession = useCallback(
    (sessionId: string) => {
      if (entities[sessionId]) {
        dispatch(setActiveSession(sessionId));
      }
    },
    [dispatch, entities],
  );

  // Focus some session belonging to the given project. If any session exists
  // in the project, picks the most recently updated non-terminal one and
  // dispatches setActiveSession. If none exist, routes the user to the
  // ProjectsPanel so they can create one. Returns true if a session was
  // focused.
  const focusProject = useCallback(
    (projectId: string): boolean => {
      const candidates = sessions
        .filter((s: Session) => s.project_id === projectId)
        .sort((a: Session, b: Session) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
      const nonTerminal = candidates.find(
        (s: Session) => s.status !== "concluding" && s.status !== "concluded" && s.status !== "interrupted",
      );
      const pick = nonTerminal ?? candidates[0];
      if (pick) {
        dispatch(setActiveSession(pick.id));
        return true;
      }
      dispatch(setLeftTab("projects"));
      return false;
    },
    [dispatch, sessions],
  );

  const refresh = useCallback(() => {
    dispatch(loadSessions());
  }, [dispatch]);

  return {
    sessions,
    rootSessions,
    ids,
    entities,
    activeSessionId,
    initialized,
    loading,
    getChildSessions,
    createSession,
    deleteSession,
    selectSession,
    focusProject,
    refresh,
  };
}
