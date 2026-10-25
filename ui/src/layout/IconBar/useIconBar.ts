import { useCallback } from "react";
import { setLeftTab } from "@/store/uiSlice";
import { TOGGLE_LEFT_PANEL_EVENT } from "@/hooks/useKeyboardShortcuts";
import type { LeftTab } from "@/store/uiSlice";
import type { AppDispatch } from "@/store";

interface UseIconBarParams {
  dispatch: AppDispatch;
  activeTab: LeftTab;
  leftPanelCollapsed: boolean;
  compact: boolean;
}

export function useIconBar({ dispatch, activeTab, leftPanelCollapsed, compact }: UseIconBarParams) {
  const setTab = useCallback(
    (tab: LeftTab) => dispatch(setLeftTab(tab)),
    [dispatch],
  );

  const handleFocusToggle = useCallback(() => {
    if (compact) {
      setTab("chat");
    } else {
      window.dispatchEvent(new Event(TOGGLE_LEFT_PANEL_EVENT));
    }
  }, [compact, setTab]);

  const isFocusActive = compact ? activeTab === "chat" : leftPanelCollapsed;

  return { setTab, handleFocusToggle, isFocusActive };
}
