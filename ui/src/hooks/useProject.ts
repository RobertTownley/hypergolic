import { useCallback } from "react";
import { useAppSelector } from "@/store";
import {
  selectActiveProject,
  selectActiveProjectId,
  selectProjectsInitialized,
  selectProjectsLoading,
} from "@/store/selectors";
import { useSessions } from "@/hooks/useSession";

/**
 * Hook for accessing and managing the active project
 */
export function useActiveProject() {
  const project = useAppSelector(selectActiveProject);
  const projectId = useAppSelector(selectActiveProjectId);
  const initialized = useAppSelector(selectProjectsInitialized);
  const loading = useAppSelector(selectProjectsLoading);
  const { focusProject } = useSessions();

  // "Switching project" now means "focus a session in that project"
  // (projects aren't focus primitives anymore). If the project has no
  // sessions, the ProjectsPanel tab opens so the user can create one.
  const switchProject = useCallback(
    (id: string) => {
      focusProject(id);
    },
    [focusProject],
  );

  return {
    project,
    projectId,
    initialized,
    loading,
    switchProject,
  };
}

/**
 * Hook for project list operations
 */
