import { combineReducers, configureStore } from "@reduxjs/toolkit";
import { reducers, type RootState } from "@/store";
import type { Project, Session } from "@/types/api";

const rootReducer = combineReducers(reducers);

export function createTestStore(preloadedState?: Partial<RootState>) {
  return configureStore({ reducer: rootReducer, preloadedState });
}

export type TestStore = ReturnType<typeof createTestStore>;

export function makeSession(overrides: Partial<Session> = {}): Session {
  return {
    id: "s-1",
    model_tier: "High",
    project_id: "p1",
    project_name: "Test",
    role: "generalist",
    status: "idle",
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
    message_count: 0,
    workflow_id: null,
    workflow_name: null,
    workflow_state_id: null,
    workflow_state_name: null,
    parent_id: null,
    description: null,
    conclusion_rating: null,
    conclusion_feedback: null,
    concluded_at: null,
    ...overrides,
  };
}

export function makeProject(overrides: Partial<Project> = {}): Project {
  return {
    id: "p-1",
    name: "Test",
    path: "/test",
    last_session_at: null,
    ...overrides,
  };
}
