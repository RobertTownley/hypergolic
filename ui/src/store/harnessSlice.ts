import { createAsyncThunk, createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { FileNode, FileContentResponse } from "@/types/api";
import { fetchHarnessFileTree, fetchHarnessFileContent } from "@/api/files";
import { dedupeCondition } from "@/store/dedupeThunk";
import type { RootState } from "@/store";

export interface HarnessState {
  tree: FileNode[];
  // Set once the tree has loaded successfully; consumers fetch only while
  // false, so remounting the harness tab does not refetch.
  treeLoaded: boolean;
  loading: boolean;
  error: string | null;
  selectedPath: string | null;
  // Per-path content cache; survives selection changes and tab switches.
  // Cleared only by invalidateHarnessContent (explicit refresh).
  contentByPath: Record<string, FileContentResponse>;
  expandedPaths: string[];
  fileLoading: boolean;
  fileError: string | null;
}

// loading starts true so the explorer shows a spinner on the frame between
// first mount and the initial loadHarnessTree dispatch.
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

export const loadHarnessTree = createAsyncThunk(
  "harness/loadTree",
  async () => fetchHarnessFileTree(),
  { condition: dedupeCondition<void>("harness/loadTree") },
);

const dedupeFileContent = dedupeCondition<{ path: string }>(
  "harness/loadFileContent",
  (arg) => arg.path,
);

export const loadHarnessFileContent = createAsyncThunk(
  "harness/loadFileContent",
  async ({ path }: { path: string }) => fetchHarnessFileContent(path),
  {
    condition: (arg, { getState }) => {
      // Cache hit: the viewer reads from contentByPath, no fetch needed.
      const { harness } = getState() as { harness: HarnessState };
      if (harness.contentByPath[arg.path]) return false;
      return dedupeFileContent(arg);
    },
  },
);

const harnessSlice = createSlice({
  name: "harness",
  initialState,
  reducers: {
    selectHarnessFile(state, action: PayloadAction<string>) {
      state.selectedPath = action.payload;
      state.fileError = null;
      // Cached files render immediately; only uncached selections show the
      // loading state (the content thunk is dispatched by the hook).
      state.fileLoading = !state.contentByPath[action.payload];
    },
    setHarnessExpandedPaths(state, action: PayloadAction<string[]>) {
      state.expandedPaths = action.payload;
    },
    // Explicit refresh: drop cached content so re-reads hit the server.
    // Selection and expansion survive; the hook re-fetches the open file.
    invalidateHarnessContent(state) {
      state.contentByPath = {};
      state.fileError = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(loadHarnessTree.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(loadHarnessTree.fulfilled, (state, action) => {
        state.loading = false;
        state.treeLoaded = true;
        state.tree = action.payload.tree;
      })
      .addCase(loadHarnessTree.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message ?? "Failed to load harness files";
      })
      .addCase(loadHarnessFileContent.pending, (state, action) => {
        // Late responses for files the user has clicked away from must not
        // toggle the flags of the file currently being viewed.
        if (action.meta.arg.path !== state.selectedPath) return;
        state.fileLoading = true;
        state.fileError = null;
      })
      .addCase(loadHarnessFileContent.fulfilled, (state, action) => {
        state.contentByPath[action.meta.arg.path] = action.payload;
        if (action.meta.arg.path === state.selectedPath) state.fileLoading = false;
      })
      .addCase(loadHarnessFileContent.rejected, (state, action) => {
        if (action.meta.arg.path !== state.selectedPath) return;
        state.fileLoading = false;
        state.fileError = action.error.message ?? "Failed to read file";
      });
  },
});

export const selectHarnessTree = (state: RootState) => state.harness.tree;
export const selectHarnessTreeLoaded = (state: RootState) => state.harness.treeLoaded;
export const selectHarnessLoading = (state: RootState) => state.harness.loading;
export const selectHarnessError = (state: RootState) => state.harness.error;
export const selectHarnessSelectedPath = (state: RootState) => state.harness.selectedPath;
export const selectHarnessFileContent = (state: RootState): FileContentResponse | null =>
  state.harness.selectedPath
    ? state.harness.contentByPath[state.harness.selectedPath] ?? null
    : null;
export const selectHarnessFileLoading = (state: RootState) => state.harness.fileLoading;
export const selectHarnessFileError = (state: RootState) => state.harness.fileError;
export const selectHarnessExpandedPaths = (state: RootState) => state.harness.expandedPaths;

export const { selectHarnessFile, setHarnessExpandedPaths, invalidateHarnessContent } =
  harnessSlice.actions;
export default harnessSlice.reducer;
