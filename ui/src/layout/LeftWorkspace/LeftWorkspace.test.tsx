import { describe, it, expect, vi, beforeAll } from "vitest";
import { render } from "@testing-library/react";
import { Provider } from "react-redux";
import { LeftWorkspace } from "./LeftWorkspace";
import { setLeftTab, type LeftTab } from "@/store/uiSlice";
import { setActiveSession, upsertSession } from "@/store/sessionsSlice";
import { createTestStore, makeSession } from "@/test/fixtures";

vi.mock("@/layout/LeftSidebar", () => ({
  LeftSidebar: () => <div data-testid="left-sidebar" />,
}));
vi.mock("@/files/DiffViewer", () => ({
  DiffViewer: () => <div data-testid="diff-viewer" />,
}));
vi.mock("@/git/GitWorkspaceView", () => ({
  GitWorkspaceView: () => <div data-testid="git-workspace" />,
}));
vi.mock("@/files/FileViewer", () => ({
  FileViewer: () => <div data-testid="file-viewer" />,
}));
vi.mock("@/projects/ProjectsPanel", () => ({
  ProjectsPanel: () => <div data-testid="projects-panel" />,
}));
vi.mock("@/analytics", () => ({
  AnalyticsPanel: () => <div data-testid="analytics-panel" />,
}));
vi.mock("@/docs/DocsViewer", () => ({
  DocsViewer: () => <div data-testid="docs-viewer" />,
}));
vi.mock("@/chat/ChatView", () => ({
  ChatView: () => <div data-testid="chat-view" />,
}));
vi.mock("@/layout/RightSidebar", () => ({
  RightSidebar: () => <div data-testid="right-sidebar" />,
}));
vi.mock("@/hooks/useAttachSelection", () => ({
  useAttachSelection: () => vi.fn(),
}));

beforeAll(() => {
  // ResizeObserver stub for useStackedLayout
  if (!("ResizeObserver" in window)) {
    (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

function renderWorkspace(tab: LeftTab, opts?: { withActiveSession?: boolean }) {
  const store = createTestStore();
  store.dispatch(setLeftTab(tab));
  if (opts?.withActiveSession) {
    store.dispatch(upsertSession(makeSession({ id: "s-1" })));
    store.dispatch(setActiveSession("s-1"));
  }
  return render(
    <Provider store={store}>
      <LeftWorkspace />
    </Provider>,
  );
}

describe("LeftWorkspace main content", () => {
  it("renders GitWorkspaceView for git tab with active session (no diff)", () => {
    const { queryByTestId } = renderWorkspace("git", { withActiveSession: true });
    expect(queryByTestId("git-workspace")).not.toBeNull();
  });

  it.each<[LeftTab, string[]]>([
    ["git", ["git-workspace", "diff-viewer"]],
    ["files", ["file-viewer"]],
    ["help", ["docs-viewer"]],
  ])("renders nothing in main content for %s tab without active session", (tab, absentIds) => {
    const { queryByTestId } = renderWorkspace(tab);
    for (const id of absentIds) expect(queryByTestId(id)).toBeNull();
  });

  it("still renders ProjectsPanel without a session", () => {
    const { queryByTestId } = renderWorkspace("projects");
    expect(queryByTestId("projects-panel")).not.toBeNull();
  });
});
