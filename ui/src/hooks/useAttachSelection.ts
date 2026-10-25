import { useCallback } from "react";
import { useAppDispatch, useAppSelector } from "@/store";
import { addDraftCodeSelection } from "@/store/uiSlice";
import { FOCUS_CHAT_EVENT } from "@/hooks/useKeyboardShortcuts";
import type { CodeSelection } from "@/types/api";

export function useAttachSelection() {
  const dispatch = useAppDispatch();
  const activeSessionId = useAppSelector((s) => s.sessions.activeSessionId);

  return useCallback(
    (selection: CodeSelection) => {
      if (activeSessionId) {
        dispatch(addDraftCodeSelection({ sessionId: activeSessionId, selection }));
        window.dispatchEvent(new Event(FOCUS_CHAT_EVENT));
      }
    },
    [dispatch, activeSessionId],
  );
}
