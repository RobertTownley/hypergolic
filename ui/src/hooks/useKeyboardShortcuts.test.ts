// @vitest-environment jsdom
import { describe, it, expect, vi } from "vitest";
import {
  runHotkeyBinding,
  EXPORT_SESSION_EVENT,
  FOCUS_CHAT_EVENT,
  NEW_SESSION_EVENT,
  CONCLUDE_SESSION_EVENT,
  TOGGLE_LEFT_PANEL_EVENT,
  TOGGLE_RIGHT_PANEL_EVENT,
} from "./useKeyboardShortcuts";
import { createTestStore } from "@/test/fixtures";

describe("runHotkeyBinding", () => {
  it("tab bindings set leftTab and uncollapse the panel", () => {
    const store = createTestStore();
    store.dispatch({ type: "ui/setLeftPanelCollapsed", payload: true });
    runHotkeyBinding({ hotkey: "Mod+5", kind: "tab", tab: "help" }, store.dispatch, "s-1");
    expect(store.getState().ui.leftTab).toBe("help");
    expect(store.getState().ui.leftPanelCollapsed).toBe(false);
  });

  it("session-scoped tab bindings are no-ops without an active session", () => {
    const store = createTestStore();
    const before = store.getState().ui.leftTab;
    for (const tab of ["git", "files", "help"] as const) {
      runHotkeyBinding({ hotkey: "Mod+1", kind: "tab", tab }, store.dispatch, null);
      expect(store.getState().ui.leftTab).toBe(before);
    }
  });

  it("non-session-scoped tab bindings fire without an active session", () => {
    const store = createTestStore();
    runHotkeyBinding({ hotkey: "Mod+3", kind: "tab", tab: "projects" }, store.dispatch, null);
    expect(store.getState().ui.leftTab).toBe("projects");
  });

  it("harness binding (Mod+4) navigates to harness tab", () => {
    const store = createTestStore();
    runHotkeyBinding({ hotkey: "Mod+4", kind: "tab", tab: "harness" }, store.dispatch);
    expect(store.getState().ui.leftTab).toBe("harness");
    expect(store.getState().ui.leftPanelCollapsed).toBe(false);
  });

  it("event bindings dispatch the named window event", () => {
    const store = createTestStore();
    const events = [
      EXPORT_SESSION_EVENT,
      FOCUS_CHAT_EVENT,
      NEW_SESSION_EVENT,
      CONCLUDE_SESSION_EVENT,
      TOGGLE_LEFT_PANEL_EVENT,
      TOGGLE_RIGHT_PANEL_EVENT,
    ];
    for (const event of events) {
      const handler = vi.fn();
      window.addEventListener(event, handler);
      runHotkeyBinding({ hotkey: "Mod+0", kind: "event", event }, store.dispatch);
      expect(handler).toHaveBeenCalledTimes(1);
      window.removeEventListener(event, handler);
    }
  });
});
