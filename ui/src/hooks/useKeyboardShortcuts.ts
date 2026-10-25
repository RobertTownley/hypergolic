import { useHotkey, type RegisterableHotkey } from "@tanstack/react-hotkeys";
import { useAppDispatch, useAppSelector, type AppDispatch } from "@/store";
import { setLeftTab, setLeftPanelCollapsed, type LeftTab } from "@/store/uiSlice";
import { selectActiveSessionId } from "@/store/selectors";
import { FILE_FINDER_OPEN_EVENT } from "@/files/FileFinder";
import { track } from "@/api/events";

const SESSION_SCOPED_TABS = new Set<LeftTab>(["git", "files", "help"]);

export const FOCUS_CHAT_EVENT = "hypergolic:focus-chat";
export const NEW_SESSION_EVENT = "hypergolic:new-session";
export const CONCLUDE_SESSION_EVENT = "hypergolic:conclude-session";
export const EXPORT_SESSION_EVENT = "hypergolic:export-session";
export const TOGGLE_LEFT_PANEL_EVENT = "hypergolic:toggle-left-panel";
export const TOGGLE_RIGHT_PANEL_EVENT = "hypergolic:toggle-right-panel";
export const JUMP_TO_SESSION_EVENT = "hypergolic:jump-to-session";
export const SCROLL_CONVO_UP_EVENT = "hypergolic:scroll-convo-up";
export const SCROLL_CONVO_DOWN_EVENT = "hypergolic:scroll-convo-down";
export const SCROLL_CONVO_TOP_EVENT = "hypergolic:scroll-convo-top";
export const SCROLL_CONVO_BOTTOM_EVENT = "hypergolic:scroll-convo-bottom";

type TabHotkey = { hotkey: RegisterableHotkey; kind: "tab"; tab: LeftTab };
type EventHotkey = { hotkey: RegisterableHotkey; kind: "event"; event: string };

const HOTKEY_BINDINGS: ReadonlyArray<TabHotkey | EventHotkey> = [
  { hotkey: "Mod+0", kind: "event", event: TOGGLE_LEFT_PANEL_EVENT },
  { hotkey: "Mod+1", kind: "tab", tab: "git" },
  { hotkey: "Mod+2", kind: "tab", tab: "files" },
  { hotkey: "Mod+3", kind: "tab", tab: "projects" },
  { hotkey: "Mod+4", kind: "tab", tab: "harness" },
  { hotkey: "Mod+5", kind: "tab", tab: "help" },
  { hotkey: "Mod+7", kind: "tab", tab: "analytics" },
  { hotkey: "Mod+8", kind: "event", event: TOGGLE_RIGHT_PANEL_EVENT },
  { hotkey: "Mod+/", kind: "event", event: FOCUS_CHAT_EVENT },
  { hotkey: "Mod+N", kind: "event", event: NEW_SESSION_EVENT },
  { hotkey: "Mod+Enter", kind: "event", event: CONCLUDE_SESSION_EVENT },
  { hotkey: "Mod+E", kind: "event", event: EXPORT_SESSION_EVENT },
  { hotkey: "Mod+P", kind: "event", event: FILE_FINDER_OPEN_EVENT },
  { hotkey: "Mod+J", kind: "event", event: JUMP_TO_SESSION_EVENT },
  { hotkey: "Mod+Shift+J", kind: "event", event: SCROLL_CONVO_UP_EVENT },
  { hotkey: "Mod+Shift+K", kind: "event", event: SCROLL_CONVO_DOWN_EVENT },
  { hotkey: "Mod+Shift+H", kind: "event", event: SCROLL_CONVO_TOP_EVENT },
  { hotkey: "Mod+Shift+L", kind: "event", event: SCROLL_CONVO_BOTTOM_EVENT },
];

export function runHotkeyBinding(
  binding: TabHotkey | EventHotkey,
  dispatch: AppDispatch,
  activeSessionId: string | null = null,
) {
  track("hotkey.used", { hotkey: String(binding.hotkey) }, activeSessionId);
  switch (binding.kind) {
    case "tab":
      if (SESSION_SCOPED_TABS.has(binding.tab) && !activeSessionId) return;
      dispatch(setLeftPanelCollapsed(false));
      dispatch(setLeftTab(binding.tab));
      return;
    case "event":
      window.dispatchEvent(new Event(binding.event));
      return;
  }
}

export function useKeyboardShortcuts() {
  const dispatch = useAppDispatch();
  const activeSessionId = useAppSelector(selectActiveSessionId);

  // The binding table is module-level and immutable, so the hook count is
  // static across renders. This loop is safe w.r.t. the Rules of Hooks even
  // though the lint rule can't verify that statically.
  for (const binding of HOTKEY_BINDINGS) {
    // oxlint-disable-next-line react/rules-of-hooks
    useHotkey(binding.hotkey, () => runHotkeyBinding(binding, dispatch, activeSessionId));
  }
}
