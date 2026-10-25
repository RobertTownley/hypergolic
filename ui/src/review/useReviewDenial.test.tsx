import { describe, it, expect } from "vitest";
import { renderHook } from "@testing-library/react";
import { Provider } from "react-redux";
import type { ReactNode } from "react";
import { createTestStore } from "@/test/fixtures";
import { addComment, setOverallNote } from "@/store/reviewSlice";
import { useReviewDenial } from "./useReviewDenial";

function setup(prepare: (store: ReturnType<typeof createTestStore>) => void) {
  const store = createTestStore();
  prepare(store);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <Provider store={store}>{children}</Provider>
  );
  return renderHook(() => useReviewDenial("s1"), { wrapper }).result;
}

describe("useReviewDenial", () => {
  it("carries the takeover's overall note into a card denial", () => {
    const { current } = setup((store) => {
      store.dispatch(setOverallNote({ sessionId: "s1", note: "  rework the fix  " }));
    });
    expect(current.reason()).toBe("rework the fix");
    expect(current.annotations).toBeUndefined();
  });

  it("keeps both the typed reason and the drafted note", () => {
    const { current } = setup((store) => {
      store.dispatch(setOverallNote({ sessionId: "s1", note: "note" }));
    });
    expect(current.reason("typed")).toBe("typed\n\nnote");
  });

  it("points at inline comments when no prose was written", () => {
    const { current } = setup((store) => {
      store.dispatch(addComment({
        sessionId: "s1",
        comment: { id: "c1", path: "a.py", line: 2, side: "new", text: "no" },
      }));
    });
    expect(current.reason()).toBe("See inline review comments.");
    expect(current.annotations).toHaveLength(1);
  });

  it("is undefined with no draft at all", () => {
    const { current } = setup(() => {});
    expect(current.reason()).toBeUndefined();
    expect(current.annotations).toBeUndefined();
  });
});
