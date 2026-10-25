import { describe, it, expect, vi, beforeEach } from "vitest";
import harnessReducer, {
  loadHarnessTree,
  loadHarnessFileContent,
  selectHarnessFile,
  invalidateHarnessContent,
  type HarnessState,
} from "./harnessSlice";
import { makeSliceStore, pending, fulfilled, rejected } from "@/test/store";
import * as filesApi from "@/api/files";
import type { FileContentResponse, FileNode } from "@/types/api";

vi.mock("@/api/files");

const initialState: HarnessState = {
  tree: [],
  treeLoaded: false,
  loading: true,
  error: null,
  selectedPath: null,
  contentByPath: {},
  expandedPaths: [],
  fileLoading: false,
  fileError: null,
};

const sampleTree: FileNode[] = [
  {
    name: "commands",
    path: "commands",
    is_dir: true,
    git_status: null,
    children: [
      { name: "review.md", path: "commands/review.md", is_dir: false, git_status: null, children: null },
    ],
  },
];

function makeContent(path: string, overrides: Partial<FileContentResponse> = {}): FileContentResponse {
  return { session_id: "", path, content: `contents of ${path}`, language: "markdown", ...overrides };
}

function contentAction(
  type: string,
  path: string,
  extra: Record<string, unknown> = {},
) {
  return { type, meta: { arg: { path } }, ...extra };
}

describe("harnessSlice", () => {
  it("returns the initial state", () => {
    expect(harnessReducer(undefined, { type: "unknown" })).toEqual(initialState);
  });

  describe("selectHarnessFile", () => {
    it("selects an uncached path and enters the loading state", () => {
      const prior: HarnessState = { ...initialState, fileError: "old error" };
      const state = harnessReducer(prior, selectHarnessFile("commands/review.md"));
      expect(state.selectedPath).toBe("commands/review.md");
      expect(state.fileLoading).toBe(true);
      expect(state.fileError).toBeNull();
    });

    it("selects a cached path without entering the loading state", () => {
      const prior: HarnessState = {
        ...initialState,
        contentByPath: { "commands/review.md": makeContent("commands/review.md") },
      };
      const state = harnessReducer(prior, selectHarnessFile("commands/review.md"));
      expect(state.selectedPath).toBe("commands/review.md");
      expect(state.fileLoading).toBe(false);
    });
  });

  it("invalidateHarnessContent drops the cache but keeps selection and expansion", () => {
    const prior: HarnessState = {
      ...initialState,
      selectedPath: "commands/review.md",
      expandedPaths: ["commands"],
      contentByPath: { "commands/review.md": makeContent("commands/review.md") },
      fileError: "stale",
    };
    const state = harnessReducer(prior, invalidateHarnessContent());
    expect(state.contentByPath).toEqual({});
    expect(state.fileError).toBeNull();
    expect(state.selectedPath).toBe("commands/review.md");
    expect(state.expandedPaths).toEqual(["commands"]);
  });

  describe("loadHarnessTree lifecycle", () => {
    it("pending sets loading and clears the error", () => {
      const prior: HarnessState = { ...initialState, loading: false, error: "old" };
      const state = harnessReducer(prior, pending(loadHarnessTree));
      expect(state.loading).toBe(true);
      expect(state.error).toBeNull();
    });

    it("fulfilled stores the tree and marks it loaded", () => {
      const state = harnessReducer(initialState, fulfilled(loadHarnessTree, { session_id: "", root: "/home/u/.hypergolic", tree: sampleTree }));
      expect(state.loading).toBe(false);
      expect(state.treeLoaded).toBe(true);
      expect(state.tree).toEqual(sampleTree);
    });

    it("rejected surfaces the error", () => {
      const state = harnessReducer(initialState, rejected(loadHarnessTree, "boom"));
      expect(state.loading).toBe(false);
      expect(state.error).toBe("boom");
      expect(state.treeLoaded).toBe(false);
    });
  });

  describe("loadHarnessFileContent lifecycle", () => {
    const selected: HarnessState = { ...initialState, selectedPath: "a.md" };

    it("pending sets fileLoading for the selected path", () => {
      const state = harnessReducer(
        selected,
        contentAction(loadHarnessFileContent.pending.type, "a.md"),
      );
      expect(state.fileLoading).toBe(true);
      expect(state.fileError).toBeNull();
    });

    it("pending for a non-selected path leaves the flags alone", () => {
      const state = harnessReducer(
        selected,
        contentAction(loadHarnessFileContent.pending.type, "other.md"),
      );
      expect(state.fileLoading).toBe(false);
    });

    it("fulfilled caches by path and clears fileLoading when selected", () => {
      const loading: HarnessState = { ...selected, fileLoading: true };
      const state = harnessReducer(
        loading,
        contentAction(loadHarnessFileContent.fulfilled.type, "a.md", {
          payload: makeContent("a.md"),
        }),
      );
      expect(state.contentByPath["a.md"]).toEqual(makeContent("a.md"));
      expect(state.fileLoading).toBe(false);
    });

    it("fulfilled for a non-selected path caches without touching the flags", () => {
      const loading: HarnessState = { ...selected, fileLoading: true };
      const state = harnessReducer(
        loading,
        contentAction(loadHarnessFileContent.fulfilled.type, "other.md", {
          payload: makeContent("other.md"),
        }),
      );
      expect(state.contentByPath["other.md"]).toEqual(makeContent("other.md"));
      expect(state.fileLoading).toBe(true);
    });

    it("rejected surfaces the error only for the selected path", () => {
      const loading: HarnessState = { ...selected, fileLoading: true };
      const state = harnessReducer(
        loading,
        contentAction(loadHarnessFileContent.rejected.type, "a.md", {
          error: { message: "nope" },
        }),
      );
      expect(state.fileLoading).toBe(false);
      expect(state.fileError).toBe("nope");

      const ignored = harnessReducer(
        loading,
        contentAction(loadHarnessFileContent.rejected.type, "other.md", {
          error: { message: "nope" },
        }),
      );
      expect(ignored.fileError).toBeNull();
      expect(ignored.fileLoading).toBe(true);
    });
  });
});

describe("harnessSlice thunks (store dispatch)", () => {
  const makeStore = () => makeSliceStore({ harness: harnessReducer });

  beforeEach(() => {
    vi.mocked(filesApi.fetchHarnessFileTree).mockReset();
    vi.mocked(filesApi.fetchHarnessFileContent).mockReset();
  });

  it("dedupes concurrent tree loads", async () => {
    let resolve!: (v: { session_id: string; root: string; tree: FileNode[] }) => void;
    vi.mocked(filesApi.fetchHarnessFileTree).mockReturnValue(
      new Promise((r) => { resolve = r; }),
    );

    const store = makeStore();
    const p1 = store.dispatch(loadHarnessTree());
    const p2 = store.dispatch(loadHarnessTree());
    resolve({ session_id: "", root: "/r", tree: sampleTree });
    await Promise.all([p1, p2]);

    expect(filesApi.fetchHarnessFileTree).toHaveBeenCalledTimes(1);
    expect(store.getState().harness.tree).toEqual(sampleTree);
    expect(store.getState().harness.treeLoaded).toBe(true);
  });

  it("fetches file content once and serves the cache thereafter", async () => {
    vi.mocked(filesApi.fetchHarnessFileContent).mockResolvedValue(makeContent("a.md"));
    const store = makeStore();
    store.dispatch(selectHarnessFile("a.md"));

    await store.dispatch(loadHarnessFileContent({ path: "a.md" }));
    expect(filesApi.fetchHarnessFileContent).toHaveBeenCalledTimes(1);

    // Second dispatch is skipped by the cache condition, not just deduped.
    await store.dispatch(loadHarnessFileContent({ path: "a.md" }));
    expect(filesApi.fetchHarnessFileContent).toHaveBeenCalledTimes(1);
    expect(store.getState().harness.contentByPath["a.md"]).toEqual(makeContent("a.md"));
    expect(store.getState().harness.fileLoading).toBe(false);
  });

  it("refetches content after invalidateHarnessContent", async () => {
    vi.mocked(filesApi.fetchHarnessFileContent)
      .mockResolvedValueOnce(makeContent("a.md", { content: "v1" }))
      .mockResolvedValueOnce(makeContent("a.md", { content: "v2" }));
    const store = makeStore();
    store.dispatch(selectHarnessFile("a.md"));

    await store.dispatch(loadHarnessFileContent({ path: "a.md" }));
    store.dispatch(invalidateHarnessContent());
    await store.dispatch(loadHarnessFileContent({ path: "a.md" }));

    expect(filesApi.fetchHarnessFileContent).toHaveBeenCalledTimes(2);
    expect(store.getState().harness.contentByPath["a.md"]?.content).toBe("v2");
  });

  it("recovers from a failed content load on re-select", async () => {
    vi.mocked(filesApi.fetchHarnessFileContent)
      .mockRejectedValueOnce(new Error("read failed"))
      .mockResolvedValueOnce(makeContent("a.md"));
    const store = makeStore();
    store.dispatch(selectHarnessFile("a.md"));

    await store.dispatch(loadHarnessFileContent({ path: "a.md" }));
    expect(store.getState().harness.fileError).toBe("read failed");
    expect(store.getState().harness.fileLoading).toBe(false);

    // Nothing was cached, so a fresh dispatch fetches again.
    store.dispatch(selectHarnessFile("a.md"));
    await store.dispatch(loadHarnessFileContent({ path: "a.md" }));
    expect(filesApi.fetchHarnessFileContent).toHaveBeenCalledTimes(2);
    expect(store.getState().harness.fileError).toBeNull();
    expect(store.getState().harness.contentByPath["a.md"]).toEqual(makeContent("a.md"));
  });
});
