import { createAsyncThunk, createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { Annotation, GitReviewResponse, RepoScope } from "@/types/api";
import { fetchGitReview, type CandidateSpan } from "@/api/git";
import { dedupeCondition } from "@/store/dedupeThunk";
import { addKeyedCases, asyncEntry, type AsyncEntry } from "@/store/asyncMap";

export interface ReviewComment {
  id: string;
  path: string;
  line: number;
  side: "old" | "new";
  text: string;
}

export type DiffMode = "unified" | "split";

interface SessionReviewState {
  manuallyOpen: boolean;
  dismissedToolUseIds: Record<string, true>;
  viewed: Record<string, boolean>;
  comments: ReviewComment[];
  annotations: Annotation[];
  selectedPath: string | null;
  diffMode: DiffMode;
  overallNote: string;
  review: AsyncEntry<GitReviewResponse | null>;
}

interface ReviewState {
  bySession: Record<string, SessionReviewState>;
}

const initialState: ReviewState = { bySession: {} };

export function commentsToAnnotations(comments: ReviewComment[]): Annotation[] | undefined {
  if (comments.length === 0) return undefined;
  return comments.map((c, i) => ({
    id: c.id,
    highlighted_text: `${c.path}:${c.line}${c.side === "old" ? " (removed line)" : ""}`,
    comment: c.text,
    position: i,
  }));
}

function ensure(state: ReviewState, sessionId: string): SessionReviewState {
  if (!state.bySession[sessionId]) {
    state.bySession[sessionId] = {
      manuallyOpen: false,
      dismissedToolUseIds: {},
      viewed: {},
      comments: [],
      annotations: [],
      selectedPath: null,
      diffMode: "unified",
      overallNote: "",
      review: asyncEntry<GitReviewResponse | null>(null),
    };
  }
  return state.bySession[sessionId];
}

// Single source of truth for the git review fetch. Every consumer (merge
// review takeover, publish-PR commit list) dispatches this and reads the
// per-session slot; concurrent dispatches for the same session collapse to
// one request via the dedupeThunk middleware.
interface LoadGitReviewArg {
  sessionId: string;
  repoScope?: RepoScope;
  span?: CandidateSpan;
}

export const loadGitReview = createAsyncThunk(
  "review/loadGitReview",
  async ({ sessionId, repoScope, span }: LoadGitReviewArg) =>
    fetchGitReview({ sessionId, repoScope }, span),
  {
    condition: dedupeCondition<LoadGitReviewArg>(
      "review/loadGitReview",
      (arg) =>
        `${arg.sessionId}:${arg.repoScope ?? "app"}:${arg.span ? `${arg.span.base}..${arg.span.head}@${arg.span.branch ?? ""}#${arg.span.view ?? ""}` : ""}`,
    ),
  },
);

const reviewSlice = createSlice({
  name: "review",
  initialState,
  reducers: {
    openReview(state, action: PayloadAction<{ sessionId: string; toolUseId?: string }>) {
      const s = ensure(state, action.payload.sessionId);
      s.manuallyOpen = true;
      if (action.payload.toolUseId) {
        delete s.dismissedToolUseIds[action.payload.toolUseId];
      }
    },
    closeReview(state, action: PayloadAction<{ sessionId: string; toolUseId?: string }>) {
      const s = ensure(state, action.payload.sessionId);
      s.manuallyOpen = false;
      if (action.payload.toolUseId) {
        s.dismissedToolUseIds[action.payload.toolUseId] = true;
      }
    },
    toggleViewed(state, action: PayloadAction<{ sessionId: string; path: string }>) {
      const s = ensure(state, action.payload.sessionId);
      s.viewed[action.payload.path] = !s.viewed[action.payload.path];
    },
    selectReviewFile(state, action: PayloadAction<{ sessionId: string; path: string | null }>) {
      ensure(state, action.payload.sessionId).selectedPath = action.payload.path;
    },
    setDiffMode(state, action: PayloadAction<{ sessionId: string; mode: DiffMode }>) {
      ensure(state, action.payload.sessionId).diffMode = action.payload.mode;
    },
    addComment(state, action: PayloadAction<{ sessionId: string; comment: ReviewComment }>) {
      ensure(state, action.payload.sessionId).comments.push(action.payload.comment);
    },
    removeComment(state, action: PayloadAction<{ sessionId: string; commentId: string }>) {
      const s = ensure(state, action.payload.sessionId);
      s.comments = s.comments.filter((c) => c.id !== action.payload.commentId);
    },
    setOverallNote(state, action: PayloadAction<{ sessionId: string; note: string }>) {
      ensure(state, action.payload.sessionId).overallNote = action.payload.note;
    },
    addAnnotation(state, action: PayloadAction<{ sessionId: string; annotation: Annotation }>) {
      ensure(state, action.payload.sessionId).annotations.push(action.payload.annotation);
    },
    removeAnnotation(state, action: PayloadAction<{ sessionId: string; annotationId: string }>) {
      const s = ensure(state, action.payload.sessionId);
      s.annotations = s.annotations.filter((a) => a.id !== action.payload.annotationId);
    },
    clearAnnotations(state, action: PayloadAction<{ sessionId: string }>) {
      const s = state.bySession[action.payload.sessionId];
      if (s) s.annotations = [];
    },
    clearReviewState(state, action: PayloadAction<{ sessionId: string }>) {
      delete state.bySession[action.payload.sessionId];
    },
  },
  extraReducers: (builder) => {
    addKeyedCases(builder, loadGitReview, {
      entry: (s: ReviewState, k) => ensure(s, k).review,
      key: (arg) => arg.sessionId,
      data: (payload) => payload,
      failMessage: "Failed to fetch review",
    });
  },
});

export const {
  openReview,
  closeReview,
  toggleViewed,
  selectReviewFile,
  setDiffMode,
  addComment,
  removeComment,
  setOverallNote,
  addAnnotation,
  removeAnnotation,
  clearAnnotations,
  clearReviewState,
} = reviewSlice.actions;

export default reviewSlice.reducer;
