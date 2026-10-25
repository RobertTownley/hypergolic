import { createSlice } from "@reduxjs/toolkit";
import { initialState } from "@/store/workspace/state";
import { gitReducers } from "@/store/workspace/gitReducers";
import { fileReducers, sandboxReducers } from "@/store/workspace/fileReducers";
import { addGitCases } from "@/store/workspace/gitCases";
import { addFileCases } from "@/store/workspace/fileCases";
import { addSessionCases } from "@/store/workspace/sessionCases";

const workspaceSlice = createSlice({
  name: "workspace",
  initialState,
  reducers: { ...gitReducers, ...fileReducers, ...sandboxReducers },
  extraReducers: (builder) => {
    addGitCases(builder);
    addFileCases(builder);
    addSessionCases(builder);
  },
});

export const {
  setDiffMode,
  setRepoScope,
  clearDiff,
  clearActionOutput,
  clearCommitDetail,
  clearError,
  upsertGitStatus,
  selectFile,
  setExpandedFilePaths,
  setFileSource,
  setSandboxContainer,
  setSandboxRoot,
  selectSandboxFile,
  setSandboxExpandedPaths,
  refreshSandbox,
} = workspaceSlice.actions;
export default workspaceSlice.reducer;
