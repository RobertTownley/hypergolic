import { describe, it, expect } from "vitest";
import { selectJumpToSessionId, selectActiveProject, selectActiveProjectId, getProjectId } from "./selectors";
import type { RootState } from "@/store";
import type { Project, Session, SessionStatus } from "@/types/api";
import { makeSession, makeProject } from "@/test/fixtures";

function makeState(sessions: Session[], activeSessionId: string | null = null, projects?: Project[]): RootState {
  const entities: Record<string, Session> = {};
  for (const s of sessions) entities[s.id] = s;
  const pEntities: Record<string, Project> = {};
  for (const p of projects ?? []) pEntities[p.id] = p;
  return {
    sessions: {
      entities,
      ids: sessions.map((s) => s.id),
      activeSessionId,
      initialized: true,
      loading: false,
      contextBySessionId: {},
    },
    projects: {
      entities: pEntities,
      ids: (projects ?? []).map((p) => p.id),
      initialized: true,
      loading: false,
      error: null,
    },
  } as unknown as RootState;
}

describe("selectJumpToSessionId", () => {
  type Row = [name: string, sessions: [string, SessionStatus, string?][], active: string | null, expected: string | null];

  it.each<Row>([
    ["returns null when there are no sessions", [], null, null],
    ["prioritizes awaiting_approval over idle", [["idle-1", "idle"], ["approval-1", "awaiting_approval"]], null, "approval-1"],
    ["prioritizes idle over thinking", [["thinking-1", "thinking"], ["idle-1", "idle"]], null, "idle-1"],
    ["skips interrupted sessions (terminal)", [["thinking-1", "thinking"], ["interrupted-1", "interrupted"]], null, "thinking-1"],
    // interrupted is terminal, so idle wins despite being older
    ["skips interrupted even when same tier as idle",
      [["idle-1", "idle", "2024-01-01T01:00:00Z"], ["interrupted-1", "interrupted", "2024-01-01T02:00:00Z"]], null, "idle-1"],
    ["prioritizes error over thinking", [["thinking-1", "thinking"], ["error-1", "error"]], null, "error-1"],
    ["prioritizes error below idle", [["error-1", "error"], ["idle-1", "idle"]], null, "idle-1"],
    // Most recently updated thinking session wins the fallback
    ["falls back to thinking when no higher-priority sessions exist",
      [["thinking-1", "thinking", "2024-01-01T02:00:00Z"], ["thinking-2", "thinking", "2024-01-01T01:00:00Z"]], null, "thinking-1"],
    ["returns null when only concluded sessions exist", [["concluded-1", "concluded"]], null, null],
    ["returns null when only terminal sessions exist", [["concluded-1", "concluded"], ["interrupted-1", "interrupted"]], null, null],
    // active session is the top awaiting_approval — should jump to idle instead
    ["skips the active session and returns the next best when active is top priority",
      [["approval-1", "awaiting_approval"], ["idle-1", "idle"]], "approval-1", "idle-1"],
    ["returns null when there is only one session and it is already active", [["idle-1", "idle"]], "idle-1", null],
    ["breaks within-tier ties by most recently updated",
      [["idle-old", "idle", "2024-01-01T00:00:00Z"], ["idle-new", "idle", "2024-01-02T00:00:00Z"]], null, "idle-new"],
    // concluded and interrupted are filtered out of the stack entirely
    ["full priority stack: awaiting_approval > idle > error > thinking (terminal excluded)",
      [["concluded-1", "concluded"], ["thinking-1", "thinking"], ["error-1", "error"],
       ["interrupted-1", "interrupted"], ["idle-1", "idle"], ["approval-1", "awaiting_approval"]], null, "approval-1"],
    // active-idle is the only non-terminal option
    ["never jumps to concluded session even as fallback", [["active-idle", "idle"], ["concluded-1", "concluded"]], "active-idle", null],
  ])("%s", (_name, sessions, active, expected) => {
    const state = makeState(
      sessions.map(([id, status, updated_at]) => makeSession({ id, status, ...(updated_at && { updated_at }) })),
      active,
    );
    expect(selectJumpToSessionId(state)).toBe(expected);
  });

  it("prefers top-level sessions over dispatch children within a tier", () => {
    const state = makeState([
      makeSession({ id: "child", status: "idle", parent_id: "top-old", updated_at: "2024-01-02T00:00:00Z" }),
      makeSession({ id: "top-old", status: "idle", updated_at: "2024-01-01T00:00:00Z" }),
    ]);
    expect(selectJumpToSessionId(state)).toBe("top-old");
  });

  it("still picks a child when it outranks all top-level sessions", () => {
    const state = makeState([
      makeSession({ id: "top-busy", status: "thinking" }),
      makeSession({ id: "child-idle", status: "idle", parent_id: "top-busy" }),
    ]);
    expect(selectJumpToSessionId(state)).toBe("child-idle");
  });
});

describe("selectActiveProject / selectActiveProjectId (derived)", () => {
  it("returns null when no active session", () => {
    const state = makeState([], null, [makeProject({ id: "p1" })]);
    expect(selectActiveProject(state)).toBeNull();
    expect(selectActiveProjectId(state)).toBeNull();
    expect(getProjectId(state)).toBeUndefined();
  });

  it("returns the project of the active session", () => {
    const sessions = [
      makeSession({ id: "s1", project_id: "p1" }),
      makeSession({ id: "s2", project_id: "p2" }),
    ];
    const projects = [makeProject({ id: "p1", name: "Alpha" }), makeProject({ id: "p2", name: "Beta" })];
    const state = makeState(sessions, "s2", projects);
    expect(selectActiveProject(state)?.id).toBe("p2");
    expect(selectActiveProject(state)?.name).toBe("Beta");
    expect(selectActiveProjectId(state)).toBe("p2");
    expect(getProjectId(state)).toBe("p2");
  });

  it("returns null when the active session references a missing project", () => {
    const state = makeState([makeSession({ id: "s1", project_id: "p-gone" })], "s1", []);
    expect(selectActiveProject(state)).toBeNull();
    expect(selectActiveProjectId(state)).toBeNull();
  });
});
