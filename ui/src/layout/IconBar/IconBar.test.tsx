import { describe, it, expect, vi } from "vitest";
import { render, fireEvent } from "@testing-library/react";
import { Provider } from "react-redux";
import { IconBar } from "./IconBar";
import { setActiveSession, upsertSession } from "@/store/sessionsSlice";
import { createTestStore, makeSession } from "@/test/fixtures";

vi.mock("@/shared/components/Tooltip", () => ({
  Tooltip: ({ title, children }: { title: string; children: React.ReactNode }) => (
    <span data-tooltip-title={title}>{children}</span>
  ),
}));

function renderIconBar(options?: { withActiveSession?: boolean }) {
  const store = createTestStore();
  if (options?.withActiveSession) {
    store.dispatch(upsertSession(makeSession({ id: "s-1" })));
    store.dispatch(setActiveSession("s-1"));
  }
  return {
    ...render(<Provider store={store}><IconBar /></Provider>),
    store,
  };
}

function getTabNames(container: HTMLElement) {
  return Array.from(container.querySelectorAll("[data-tab]")).map(
    (el) => el.getAttribute("data-tab"),
  );
}

describe("IconBar", () => {
  it("renders the Harness button with the tool icon", () => {
    const { container } = renderIconBar();
    expect(container.querySelector(".lucide-wrench")).not.toBeNull();
  });

  it("navigates to the harness tab when the Harness button is clicked", () => {
    const { container, store } = renderIconBar();
    const btn = container.querySelector<HTMLButtonElement>("[data-tab='harness']");
    expect(btn).not.toBeNull();
    fireEvent.click(btn!);
    expect(store.getState().ui.leftTab).toBe("harness");
    expect(store.getState().ui.leftPanelCollapsed).toBe(false);
  });

  it("hides session-scoped tabs when no session is active", () => {
    const { container } = renderIconBar();
    const tabs = getTabNames(container);
    expect(tabs).not.toContain("git");
    expect(tabs).not.toContain("files");
    expect(tabs).not.toContain("help");
    expect(tabs).toContain("harness");
    expect(tabs).toContain("analytics");
  });

  it("shows session-scoped tabs once a session becomes active", () => {
    const { container } = renderIconBar({ withActiveSession: true });
    const tabs = getTabNames(container);
    expect(tabs).toContain("git");
    expect(tabs).toContain("files");
    expect(tabs).toContain("help");
  });

  it("renders tooltip titles with shortcut hints", () => {
    const { container } = renderIconBar();
    const titles = Array.from(container.querySelectorAll("[data-tooltip-title]")).map(
      (el) => el.getAttribute("data-tooltip-title"),
    );
    expect(titles).toContain("Harness (\u2318\u0034)");
    expect(titles).toContain("Analytics (\u2318\u0037)");
    expect(titles).toContain("Projects (\u2318\u0033)");
  });
});
