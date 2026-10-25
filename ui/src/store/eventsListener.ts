import { createListenerMiddleware } from "@reduxjs/toolkit";

import { track } from "@/api/events";
import type { AppDispatch, RootState } from "@/store";
import { setActiveSession } from "@/store/sessionsSlice";
import { setLeftTab } from "@/store/uiSlice";

export const eventsListener = createListenerMiddleware();
const startAppListening = eventsListener.startListening.withTypes<RootState, AppDispatch>();

startAppListening({
  actionCreator: setActiveSession,
  effect: (action, api) => {
    const prev = api.getOriginalState().sessions.activeSessionId;
    if (!action.payload || action.payload === prev) return;
    track("session.switched", { from: prev ?? null }, action.payload);
  },
});

startAppListening({
  actionCreator: setLeftTab,
  effect: (action, api) => {
    if (action.payload === api.getOriginalState().ui.leftTab) return;
    track("tab.opened", { tab: action.payload }, api.getState().sessions.activeSessionId);
  },
});
