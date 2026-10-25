import { useEffect, useRef, useCallback } from "react";
import { useAppDispatch, useAppSelector } from "@/store";
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";
import { useCompactLayout } from "@/hooks/useCompactLayout";
import { setLeftTab, toggleLeftPanel, setLeftPanelCollapsed, toggleRightPanel, loadSystemConfig } from "@/store/uiSlice";
import { TOGGLE_LEFT_PANEL_EVENT, TOGGLE_RIGHT_PANEL_EVENT } from "@/hooks/useKeyboardShortcuts";
import { loadSessions } from "@/store/sessionsSlice";
import { loadProjects } from "@/store/projectsSlice";
import { selectActiveSessionId } from "@/store/selectors";

export function useAppFrame() {
  const dispatch = useAppDispatch();
  const activeSessionId = useAppSelector(selectActiveSessionId);
  const compact = useCompactLayout();
  const prevCompact = useRef(compact);
  const leftTab = useAppSelector((s) => s.ui.leftTab);
  const leftPanelCollapsed = useAppSelector((s) => s.ui.leftPanelCollapsed);
  const rightPanelCollapsed = useAppSelector((s) => s.ui.rightPanelCollapsed);
  const prevLeftTab = useRef(leftTab);

  useKeyboardShortcuts();

  const handleToggle = useCallback(() => {
    if (compact) {
      if (leftTab === "chat") {
        const prev = prevLeftTab.current;
        const fallback = activeSessionId ? "git" : "projects";
        dispatch(setLeftTab(prev !== "chat" && prev !== "sessions" ? prev : fallback));
      } else {
        prevLeftTab.current = leftTab;
        dispatch(setLeftTab("chat"));
      }
    } else {
      dispatch(toggleLeftPanel());
    }
  }, [compact, leftTab, dispatch, activeSessionId]);

  useEffect(() => {
    window.addEventListener(TOGGLE_LEFT_PANEL_EVENT, handleToggle);
    return () => window.removeEventListener(TOGGLE_LEFT_PANEL_EVENT, handleToggle);
  }, [handleToggle]);

  const handleToggleRight = useCallback(() => {
    dispatch(toggleRightPanel());
  }, [dispatch]);

  useEffect(() => {
    window.addEventListener(TOGGLE_RIGHT_PANEL_EVENT, handleToggleRight);
    return () => window.removeEventListener(TOGGLE_RIGHT_PANEL_EVENT, handleToggleRight);
  }, [handleToggleRight]);

  useEffect(() => {
    if (compact === prevCompact.current) return;
    prevCompact.current = compact;
    if (compact) {
      dispatch(setLeftPanelCollapsed(false));
      if (leftTab !== "chat" && leftTab !== "sessions") dispatch(setLeftTab("chat"));
    } else {
      dispatch(setLeftPanelCollapsed(false));
      if (leftTab === "chat" || leftTab === "sessions") {
        dispatch(setLeftTab(activeSessionId ? "git" : "projects"));
      }
    }
  }, [compact, leftTab, dispatch, activeSessionId]);

  useEffect(() => {
    if (activeSessionId) return;
    if (leftTab === "git" || leftTab === "files" || leftTab === "help") {
      dispatch(setLeftTab("projects"));
    }
  }, [activeSessionId, leftTab, dispatch]);

  useEffect(() => {
    dispatch(loadProjects());
    dispatch(loadSessions());
    dispatch(loadSystemConfig());
  }, [dispatch]);

  return { compact, leftPanelCollapsed, rightPanelCollapsed };
}
