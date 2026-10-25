import { describe, it, expect, vi, beforeEach } from "vitest";
import { configureStore } from "@reduxjs/toolkit";
import { reducers } from "@/store";
import { setActiveSession } from "@/store/sessionsSlice";
import { setLeftTab } from "@/store/uiSlice";
import { eventsListener } from "./eventsListener";
import { track } from "@/api/events";

vi.mock("@/api/events", () => ({ track: vi.fn() }));

function makeStore() {
  return configureStore({
    reducer: reducers,
    middleware: (getDefault) => getDefault().prepend(eventsListener.middleware),
  });
}

describe("eventsListener", () => {
  beforeEach(() => vi.mocked(track).mockClear());

  it("tracks a session switch once, with the previous session", () => {
    const store = makeStore();
    store.dispatch(setActiveSession("s-a"));
    store.dispatch(setActiveSession("s-b"));
    store.dispatch(setActiveSession("s-b"));
    expect(track).toHaveBeenCalledTimes(2);
    expect(track).toHaveBeenLastCalledWith("session.switched", { from: "s-a" }, "s-b");
  });

  it("tracks a tab change but not a repeat of the same tab", () => {
    const store = makeStore();
    store.dispatch(setLeftTab("files"));
    store.dispatch(setLeftTab("files"));
    expect(track).toHaveBeenCalledTimes(1);
    expect(track).toHaveBeenCalledWith("tab.opened", { tab: "files" }, null);
  });
});
