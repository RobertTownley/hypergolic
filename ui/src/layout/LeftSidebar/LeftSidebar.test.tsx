import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import { Provider } from "react-redux";
import { LeftSidebar } from "./LeftSidebar";
import { setLeftTab, type LeftTab } from "@/store/uiSlice";
import { setActiveSession, upsertSession } from "@/store/sessionsSlice";
import { createTestStore, makeSession } from "@/test/fixtures";

vi.mock("@/git/VersionControl", () => ({
  VersionControl: () => <div data-testid="version-control" />,
}));
vi.mock("@/files/FileExplorer", () => ({
  FileExplorer: () => <div data-testid="file-explorer" />,
}));
vi.mock("@/docs/DocsPanel", () => ({
  DocsPanel: () => <div data-testid="docs-panel" />,
}));
vi.mock("@/harness/HarnessExplorer", () => ({
  HarnessExplorer: () => <div data-testid="harness-explorer" />,
}));

function renderSidebar(tab: LeftTab, opts?: { withActiveSession?: boolean }) {
  const store = createTestStore();
  if (opts?.withActiveSession) {
    store.dispatch(upsertSession(makeSession({ id: "s-1" })));
    store.dispatch(setActiveSession("s-1"));
  }
  // After setActiveSession: it resets leftTab to "git" (uiSlice extraReducer).
  store.dispatch(setLeftTab(tab));
  return render(
    <Provider store={store}>
      <LeftSidebar />
    </Provider>,
  );
}

describe("LeftSidebar", () => {
  it.each<[LeftTab, string]>([
    ["git", "version-control"],
    ["files", "file-explorer"],
    ["help", "docs-panel"],
  ])("renders the %s panel with an active session", (tab, testId) => {
    const { queryByTestId } = renderSidebar(tab, { withActiveSession: true });
    expect(queryByTestId(testId)).not.toBeNull();
  });

  it.each<[LeftTab, string]>([
    ["git", "version-control"],
    ["files", "file-explorer"],
    ["help", "docs-panel"],
  ])("renders nothing for %s tab without an active session", (tab, testId) => {
    const { queryByTestId } = renderSidebar(tab);
    expect(queryByTestId(testId)).toBeNull();
  });

  it.each([
    ["without a session", undefined],
    ["with an active session", { withActiveSession: true }],
  ])("renders nothing for harness tab %s (LeftWorkspace owns harness rendering)", (_name, opts) => {
    const { queryByTestId } = renderSidebar("harness", opts);
    expect(queryByTestId("harness-explorer")).toBeNull();
  });
});
