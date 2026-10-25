import { configureStore } from "@reduxjs/toolkit";
import { useDispatch, useSelector } from "react-redux";
import projectsReducer from "./projectsSlice";
import sessionsReducer from "./sessionsSlice";
import messagesReducer from "./messagesSlice";
import workspaceReducer from "./workspaceSlice";
import uiReducer from "./uiSlice";
import mcpReducer from "./mcpSlice";
import analyticsReducer from "./analyticsSlice";
import reviewReducer from "./reviewSlice";
import harnessReducer from "./harnessSlice";
import { dedupeTracker } from "./dedupeThunk";
import { focusListener } from "./focusListener";
import { eventsListener } from "./eventsListener";

export const reducers = {
  projects: projectsReducer,
  sessions: sessionsReducer,
  messages: messagesReducer,
  workspace: workspaceReducer,
  ui: uiReducer,
  mcp: mcpReducer,
  analytics: analyticsReducer,
  review: reviewReducer,
  harness: harnessReducer,
};

export const store = configureStore({
  reducer: reducers,
  middleware: (getDefault) =>
    getDefault().prepend(focusListener.middleware, eventsListener.middleware).concat(dedupeTracker),
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

export const useAppDispatch = useDispatch.withTypes<AppDispatch>();
export const useAppSelector = useSelector.withTypes<RootState>();
