import type { PayloadAction } from "@reduxjs/toolkit";
import type { GitStatusResponse, DiffMode, RepoScope } from "@/types/api";
import { activeSlot, writeToSlot, type WorkspaceState } from "@/store/workspace/state";

export const gitReducers = {
  setDiffMode(state: WorkspaceState, action: PayloadAction<DiffMode>) {
    state.diffMode = action.payload;
    const slot = activeSlot(state);
    if (slot) slot.selectedDiff = null;
  },
  setRepoScope(state: WorkspaceState, action: PayloadAction<RepoScope>) {
    state.repoScope = action.payload;
    // Cached git state belongs to the previous repo; drop it rather than
    // flash another repo's files while the refetch is in flight.
    const slot = activeSlot(state);
    if (slot) {
      slot.status = null;
      slot.logEntries = [];
      slot.selectedDiff = null;
      slot.commitDetail = null;
      slot.changes = null;
      slot.changesMode = null;
    }
  },
  clearDiff(state: WorkspaceState) {
    const slot = activeSlot(state);
    if (slot) slot.selectedDiff = null;
  },
  clearActionOutput(state: WorkspaceState) {
    state.actionOutput = null;
  },
  clearCommitDetail(state: WorkspaceState) {
    const slot = activeSlot(state);
    if (slot) slot.commitDetail = null;
  },
  clearError(state: WorkspaceState) {
    state.error = null;
    const slot = activeSlot(state);
    if (slot) slot.statusError = null;
  },
  upsertGitStatus(
    state: WorkspaceState,
    action: PayloadAction<{ sessionId: string; status: GitStatusResponse }>,
  ) {
    // Turn-end pushes always describe the app repo; don't stomp a
    // harness/shared view the user is looking at.
    if (state.repoScope !== "app") return;
    const { sessionId, status } = action.payload;
    writeToSlot(state, sessionId, (slot) => {
      slot.status = status;
      slot.loading = false;
    });
  },
};
