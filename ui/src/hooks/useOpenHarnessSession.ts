import { useCallback } from "react";
import { useAppDispatch } from "@/store";
import { addSession, setActiveSession } from "@/store/sessionsSlice";
import { loadProjectBranches } from "@/store/projectsSlice";
import { useWebSocket } from "@/api/WebSocketProvider";
import { HARNESS_PROJECT_ID } from "@/harness/openHarnessSession";

/**
 * Returns a function that creates a new harness session and sends an initial
 * message. The harness-engineering capability is already on the session's PATH.
 */
export function useOpenHarnessSession() {
  const dispatch = useAppDispatch();
  const { send } = useWebSocket();

  return useCallback(
    async (initialMessage: string) => {
      const { current, branches } = await dispatch(
        loadProjectBranches({ projectId: HARNESS_PROJECT_ID }),
      ).unwrap();
      const baseBranch = current || branches[0] || "";
      if (!baseBranch) {
        // Repo has no branches (no commits) — can't root a worktree. Bail.
        return;
      }
      const result = await dispatch(
        addSession({
          projectId: HARNESS_PROJECT_ID,
          baseBranch,
          modelTier: "High",
        }),
      );
      if (!addSession.fulfilled.match(result)) return;

      const session = result.payload;
      dispatch(setActiveSession(session.id));

      await send(initialMessage, session.id, "High");
    },
    [dispatch, send],
  );
}
