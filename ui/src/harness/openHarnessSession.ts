import type { AppDispatch } from "@/store";
import { addSession, setActiveSession } from "@/store/sessionsSlice";
import { setLeftTab, setLeftPanelCollapsed } from "@/store/uiSlice";
import { loadProjectBranches } from "@/store/projectsSlice";
import { fetchSessions } from "@/api/sessions";

export const HARNESS_PROJECT_ID = "harness";

/**
 * Open a chat session on the auto-registered `harness` project. Focus an
 * existing empty session if one exists, otherwise create a new session.
 * Throws on failure (caller decides how to surface errors).
 *
 * There is no longer a `setActiveProject` dispatch — the derived
 * selectActiveProjectId picks up the project from the focused session.
 */
export async function openHarnessSession(dispatch: AppDispatch): Promise<void> {
  const sessions = await fetchSessions(HARNESS_PROJECT_ID);
  const empty = sessions.find((s) => s.message_count === 0);

  if (empty) {
    dispatch(setActiveSession(empty.id));
    dispatch(setLeftPanelCollapsed(false));
    dispatch(setLeftTab("git"));
    return;
  }

  const { current, branches } = await dispatch(
    loadProjectBranches({ projectId: HARNESS_PROJECT_ID }),
  ).unwrap();
  const baseBranch = current || branches[0] || "";
  if (!baseBranch) {
    throw new Error("Harness project has no git branch");
  }

  const result = await dispatch(addSession({ projectId: HARNESS_PROJECT_ID, baseBranch }));
  if (addSession.rejected.match(result)) {
    throw new Error(result.error.message ?? "Failed to create harness session");
  }
  if (!addSession.fulfilled.match(result)) {
    throw new Error("Failed to create harness session");
  }
  dispatch(setActiveSession(result.payload.id));
  dispatch(setLeftPanelCollapsed(false));
  dispatch(setLeftTab("git"));
}
