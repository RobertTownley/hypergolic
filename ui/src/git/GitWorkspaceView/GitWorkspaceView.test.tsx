import { describe, it, expect, vi } from "vitest";
import { render, fireEvent, act } from "@testing-library/react";
import { Provider } from "react-redux";
import { GitWorkspaceView } from "./GitWorkspaceView";
import { loadGitStatus } from "@/store/workspaceThunks";
import { setActiveSession, upsertSession } from "@/store/sessionsSlice";
import { createTestStore, makeSession } from "@/test/fixtures";
import type { GitStatusResponse } from "@/types/api";

vi.mock("@/git/GitLog", () => ({
  GitLogList: () => <div data-testid="log-list" />,
}));
vi.mock("./InlineChanges", () => ({
  InlineChanges: () => <div data-testid="inline-changes" />,
}));

function makeStatus(overrides: Partial<GitStatusResponse> = {}): GitStatusResponse {
  return {
    session_id: "s-1",
    branch: "main",
    ahead: 0,
    behind: 0,
    staged: [],
    unstaged: [],
    untracked: [],
    all_changes: [],
    ...overrides,
  };
}

function setup() {
  const store = createTestStore();
  store.dispatch(upsertSession(makeSession()));
  store.dispatch(setActiveSession("s-1"));
  const dispatchStatus = (overrides: Partial<GitStatusResponse>) =>
    act(() => {
      store.dispatch({
        type: loadGitStatus.fulfilled.type,
        payload: { repoScope: "app" as const, ...makeStatus(overrides) },
        meta: { arg: { sessionId: "s-1" } },
      });
    });
  const utils = render(
    <Provider store={store}>
      <GitWorkspaceView />
    </Provider>,
  );
  return { ...utils, dispatchStatus };
}

describe("GitWorkspaceView", () => {
  it("defaults to History when the tree is clean", () => {
    const { queryByTestId, dispatchStatus } = setup();
    dispatchStatus({});
    expect(queryByTestId("log-list")).not.toBeNull();
  });

  it("auto-switches to Diff when changes appear and back when they clear", () => {
    const { queryByTestId, dispatchStatus } = setup();
    dispatchStatus({ untracked: ["new.txt"] });
    expect(queryByTestId("inline-changes")).not.toBeNull();
    dispatchStatus({});
    expect(queryByTestId("log-list")).not.toBeNull();
  });

  it("respects a manual tab choice", () => {
    const { getByRole, queryByTestId, dispatchStatus } = setup();
    dispatchStatus({ untracked: ["new.txt"] });
    fireEvent.click(getByRole("tab", { name: /history/i }));
    expect(queryByTestId("log-list")).not.toBeNull();
  });
});
