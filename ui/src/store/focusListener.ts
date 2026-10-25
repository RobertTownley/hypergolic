import { createListenerMiddleware } from "@reduxjs/toolkit";

import type { AppDispatch, RootState } from "@/store";
import { setActiveSession, removeSession } from "@/store/sessionsSlice";
import { loadGitStatus, loadBranches, loadGitLog, loadFileTree } from "@/store/workspaceThunks";

export const focusListener = createListenerMiddleware();

const startAppListening = focusListener.startListening.withTypes<RootState, AppDispatch>();

startAppListening({
  actionCreator: setActiveSession,
  effect: (action, api) => {
    const prev = api.getOriginalState().sessions.activeSessionId;
    const next = action.payload;
    if (next === prev) return;
    if (!next) return;
    api.dispatch(loadGitStatus({ sessionId: next }));
    api.dispatch(loadBranches({ sessionId: next }));
    api.dispatch(loadGitLog({ sessionId: next, count: 50 }));
    api.dispatch(loadFileTree({ sessionId: next }));
  },
});

startAppListening({
  actionCreator: removeSession.fulfilled,
  effect: (action, api) => {
    const removedId = action.payload;
    const prevActive = api.getOriginalState().sessions.activeSessionId;
    if (prevActive !== removedId) return;
    const state = api.getState();
    const nextId = state.sessions.ids[0] ?? null;
    if (nextId) {
      api.dispatch(setActiveSession(nextId));
    }
  },
});
