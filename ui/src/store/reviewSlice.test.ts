import { describe, it, expect, vi, beforeEach } from "vitest";
import reducer, {
  openReview,
  closeReview,
  toggleViewed,
  addComment,
  removeComment,
  setOverallNote,
  addAnnotation,
  removeAnnotation,
  clearAnnotations,
  clearReviewState,
  loadGitReview,
} from "./reviewSlice";
import { makeSliceStore, deferred, pending, fulfilled, rejected } from "@/test/store";
import { fetchGitReview } from "@/api/git";
import type { GitReviewResponse } from "@/types/api";

vi.mock("@/api/git", () => ({
  fetchGitReview: vi.fn(),
}));

const fetchGitReviewMock = vi.mocked(fetchGitReview);

const SID = "s1";

const REVIEW: GitReviewResponse = {
  session_id: SID,
  branch: "feat",
  base_branch: "main",
  merge_base: "abc",
  ahead: 1,
  behind: 0,
  commits: [],
  files: [],
};

describe("reviewSlice", () => {
  it("close dismisses the approval; open clears the dismissal", () => {
    let state = reducer(undefined, closeReview({ sessionId: SID, toolUseId: "tu1" }));
    expect(state.bySession[SID].dismissedToolUseIds).toEqual({ tu1: true });
    state = reducer(state, openReview({ sessionId: SID, toolUseId: "tu1" }));
    expect(state.bySession[SID].dismissedToolUseIds).toEqual({});
    expect(state.bySession[SID].manuallyOpen).toBe(true);
  });

  it("viewed state and comments survive close/reopen", () => {
    let state = reducer(undefined, toggleViewed({ sessionId: SID, path: "a.py" }));
    state = reducer(state, addComment({
      sessionId: SID,
      comment: { id: "c1", path: "a.py", line: 3, side: "new", text: "hm" },
    }));
    state = reducer(state, closeReview({ sessionId: SID, toolUseId: "tu1" }));
    state = reducer(state, openReview({ sessionId: SID, toolUseId: "tu1" }));
    expect(state.bySession[SID].viewed["a.py"]).toBe(true);
    expect(state.bySession[SID].comments).toHaveLength(1);
  });

  it("removeComment and clearReviewState", () => {
    let state = reducer(undefined, addComment({
      sessionId: SID,
      comment: { id: "c1", path: "a.py", line: 3, side: "new", text: "hm" },
    }));
    state = reducer(state, removeComment({ sessionId: SID, commentId: "c1" }));
    expect(state.bySession[SID].comments).toEqual([]);
    state = reducer(state, clearReviewState({ sessionId: SID }));
    expect(state.bySession[SID]).toBeUndefined();
  });

  it("overallNote is stored per session and survives close/reopen", () => {
    let state = reducer(undefined, setOverallNote({ sessionId: SID, note: "needs work" }));
    expect(state.bySession[SID].overallNote).toBe("needs work");
    state = reducer(state, closeReview({ sessionId: SID, toolUseId: "tu1" }));
    state = reducer(state, openReview({ sessionId: SID, toolUseId: "tu1" }));
    expect(state.bySession[SID].overallNote).toBe("needs work");
    state = reducer(state, clearReviewState({ sessionId: SID }));
    expect(state.bySession[SID]).toBeUndefined();
  });

  it("addAnnotation, removeAnnotation, and clearAnnotations", () => {
    const ann = { id: "a1", highlighted_text: "the plan", comment: "why?", position: 0 };
    let state = reducer(undefined, addAnnotation({ sessionId: SID, annotation: ann }));
    state = reducer(state, addAnnotation({
      sessionId: SID,
      annotation: { id: "a2", highlighted_text: "the risk", comment: "ok", position: 1 },
    }));
    expect(state.bySession[SID].annotations).toHaveLength(2);
    state = reducer(state, removeAnnotation({ sessionId: SID, annotationId: "a1" }));
    expect(state.bySession[SID].annotations).toEqual([
      { id: "a2", highlighted_text: "the risk", comment: "ok", position: 1 },
    ]);
    state = reducer(state, clearAnnotations({ sessionId: SID }));
    expect(state.bySession[SID].annotations).toEqual([]);
  });

  it("clearAnnotations only clears annotations, not comments", () => {
    let state = reducer(undefined, addComment({
      sessionId: SID,
      comment: { id: "c1", path: "a.py", line: 3, side: "new", text: "hm" },
    }));
    state = reducer(state, addAnnotation({
      sessionId: SID,
      annotation: { id: "a1", highlighted_text: "t", comment: "c", position: 0 },
    }));
    state = reducer(state, clearAnnotations({ sessionId: SID }));
    expect(state.bySession[SID].annotations).toEqual([]);
    expect(state.bySession[SID].comments).toHaveLength(1);
  });
});

describe("reviewSlice — loadGitReview", () => {
  it("pending sets loading and clears a prior error", () => {
    let state = reducer(undefined, rejected(loadGitReview, "boom", { sessionId: SID }));
    expect(state.bySession[SID].review.error).toBe("boom");
    state = reducer(state, pending(loadGitReview, { sessionId: SID }));
    expect(state.bySession[SID].review.loading).toBe(true);
    expect(state.bySession[SID].review.error).toBeNull();
  });

  it("fulfilled stores the review for the session", () => {
    let state = reducer(undefined, pending(loadGitReview, { sessionId: SID }));
    state = reducer(state, fulfilled(loadGitReview, REVIEW, { sessionId: SID }));
    expect(state.bySession[SID].review.loading).toBe(false);
    expect(state.bySession[SID].review.data).toEqual(REVIEW);
    expect(state.bySession["other"]).toBeUndefined();
  });

  it("rejected stores the error message", () => {
    let state = reducer(undefined, pending(loadGitReview, { sessionId: SID }));
    state = reducer(state, rejected(loadGitReview, "Failed to fetch review", { sessionId: SID }));
    expect(state.bySession[SID].review.loading).toBe(false);
    expect(state.bySession[SID].review.data).toBeNull();
    expect(state.bySession[SID].review.error).toBe("Failed to fetch review");
  });

  it("rejected falls back to a default message", () => {
    const state = reducer(undefined, rejected(loadGitReview, undefined, { sessionId: SID }));
    expect(state.bySession[SID].review.error).toBe("Failed to fetch review");
  });
});

describe("reviewSlice — loadGitReview dedupe integration", () => {
  const makeStore = () => makeSliceStore({ review: reducer });

  beforeEach(() => {
    fetchGitReviewMock.mockReset();
  });

  it("concurrent dispatches for the same session make one request", async () => {
    const { promise, resolve } = deferred<GitReviewResponse>();
    fetchGitReviewMock.mockReturnValue(promise);

    const store = makeStore();
    const p1 = store.dispatch(loadGitReview({ sessionId: SID }));
    const p2 = store.dispatch(loadGitReview({ sessionId: SID }));

    resolve(REVIEW);
    await p1;
    await p2;

    expect(fetchGitReviewMock).toHaveBeenCalledTimes(1);
    expect(store.getState().review.bySession[SID].review.data).toEqual(REVIEW);
  });

  it("does not dedupe concurrent dispatches for different sessions", async () => {
    fetchGitReviewMock.mockResolvedValue(REVIEW);

    const store = makeStore();
    await Promise.all([
      store.dispatch(loadGitReview({ sessionId: "a" })),
      store.dispatch(loadGitReview({ sessionId: "b" })),
    ]);

    expect(fetchGitReviewMock).toHaveBeenCalledTimes(2);
  });

  it("allows a fresh fetch after the previous one settles", async () => {
    fetchGitReviewMock.mockResolvedValue(REVIEW);

    const store = makeStore();
    await store.dispatch(loadGitReview({ sessionId: SID }));
    await store.dispatch(loadGitReview({ sessionId: SID }));

    expect(fetchGitReviewMock).toHaveBeenCalledTimes(2);
  });
});
