import { useState, useRef, useEffect, useCallback } from "react";
import { Spinner } from "@/shared/components/Spinner";
import { FolderOpenIcon, SquareKanbanIcon, WrenchIcon } from "lucide-react";
import { HARNESS_PROJECT_ID } from "@/harness/openHarnessSession";
import { useAppDispatch, useAppSelector } from "@/store";
import { addSession, setActiveSession, loadSessions } from "@/store/sessionsSlice";
import { setLeftTab } from "@/store/uiSlice";
import { selectActiveProjectId } from "@/store/selectors";
import { loadProjectBranches } from "@/store/projectsSlice";
import { useSessions } from "@/hooks/useSession";
import { EmptyState } from "@/shared/components/EmptyState";
import { Panel, PanelHeader, PanelBody } from "@/shared/components/Panel";
import styles from "./ProjectsPanel.module.css";

export function ProjectsPanel() {
  const dispatch = useAppDispatch();
  const { ids, entities, loading } = useAppSelector((s) => s.projects);
  const activeProjectId = useAppSelector(selectActiveProjectId);
  const { focusProject } = useSessions();
  const [focusedIndex, setFocusedIndex] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.focus();
  }, []);

  // Focus an existing session in the chosen project if possible; only
  // create a new session if the project has none. Matches the pattern
  // used everywhere else (useProject.switchProject, openHarnessSession).
  const selectProject = useCallback(async (projectId: string) => {
    if (focusProject(projectId)) {
      dispatch(setLeftTab("git"));
      return;
    }
    const { current, branches } = await dispatch(loadProjectBranches({ projectId })).unwrap();
    const baseBranch = current || branches[0] || "";
    if (!baseBranch) {
      // Repo has no branches; creating a worktree-session would fail.
      return;
    }
    const result = await dispatch(addSession({ projectId, baseBranch }));
    if (addSession.fulfilled.match(result)) {
      const sessionId = result.payload.id;
      dispatch(setActiveSession(sessionId));
      await dispatch(loadSessions());
      dispatch(setLeftTab("git"));
    }
  }, [dispatch, focusProject]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setFocusedIndex((prev) => Math.min(prev + 1, ids.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setFocusedIndex((prev) => Math.max(prev - 1, 0));
    } else if (e.key === "Enter" && ids[focusedIndex]) {
      e.preventDefault();
      selectProject(ids[focusedIndex]);
    }
  };

  if (loading) {
    return (
      <Panel>
        <EmptyState><Spinner /></EmptyState>
      </Panel>
    );
  }

  return (
    <Panel
      ref={listRef}
      className={styles.panelFocus}
      tabIndex={0}
      onKeyDown={handleKeyDown}
      style={{ outline: "none" }}
    >
      <PanelHeader icon={<SquareKanbanIcon />}>
        Projects
      </PanelHeader>

      {ids.length === 0 && (
        <EmptyState
          icon={<FolderOpenIcon style={{ fontSize: 32, color: "#2a2a3e" }} />}
          text="No projects declared"
          className={styles.emptyState}
        >
          Declare projects in your harness <code>main.py</code>.
        </EmptyState>
      )}

      <PanelBody scrollable>
        <div className={styles.projectList}>
          {ids.map((id: string, index: number) => {
            const project = entities[id];
            if (!project) return null;
            const isActive = id === activeProjectId;
            const isFocused = index === focusedIndex;
            return (
              <div
                key={id}
                className={`${styles.projectRow} ${isActive ? styles.projectRowActive : ""} ${isFocused ? styles.projectRowFocused : ""}`}
                onClick={() => selectProject(id)}
                onMouseEnter={() => setFocusedIndex(index)}
              >
                <div className={styles.projectInfo}>
                  <span className={styles.projectName}>
                    {id === HARNESS_PROJECT_ID && (
                      <WrenchIcon className={styles.projectIconHarness} />
                    )}
                    {project.name}
                  </span>
                  <span className={styles.projectPath}>
                    {project.path}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </PanelBody>
    </Panel>
  );
}
