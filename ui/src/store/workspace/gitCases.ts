import type { ActionReducerMapBuilder } from "@reduxjs/toolkit";
import type { RepoScope } from "@/types/api";
import { writeToSlot, type WorkspaceState } from "@/store/workspace/state";
import { scopedCases, actionCases } from "@/store/workspace/cases";
import {
  loadGitStatus,
  loadRepos,
  loadBranches,
  checkoutBranch,
  createBranch,
  loadGitLog,
  loadCommitDetail,
  loadChanges,
  loadDiff,
} from "@/store/workspaceThunks";

type Builder = ActionReducerMapBuilder<WorkspaceState>;

// Every scoped thunk stamps its payload with the repoScope it fetched
// for; a mismatch with the current scope means the response is stale.
const staleScope = (state: { repoScope: RepoScope }, payload: unknown) =>
  (payload as { repoScope: RepoScope }).repoScope !== state.repoScope;

function addGitReadCases(builder: Builder): void {
  builder.addCase(loadRepos.fulfilled, (state, action) => {
    writeToSlot(state, action.payload.session_id, (slot) => {
      slot.availableRepos = action.payload.repos;
    });
  });
  scopedCases(builder, loadGitStatus, {
    loading: "loading",
    error: ["statusError", "Failed to load git status"],
    dropFulfilled: staleScope,
    onFulfilled: (slot, payload) => { slot.status = payload; },
  });
  scopedCases(builder, loadBranches, {
    loading: "branchesLoading",
    onFulfilled: (slot, payload) => { slot.branches = payload.branches; },
  });
  scopedCases(builder, loadDiff, {
    loading: "diffLoading",
    dropFulfilled: staleScope,
    onFulfilled: (slot, payload) => { slot.selectedDiff = payload; },
  });
}

function addGitHistoryCases(builder: Builder): void {
  scopedCases(builder, loadGitLog, {
    loading: "logLoading",
    dropFulfilled: staleScope,
    onFulfilled: (slot, payload) => { slot.logEntries = payload.entries; },
  });
  scopedCases(builder, loadChanges, {
    loading: "changesLoading",
    dropFulfilled: staleScope,
    onPending: (slot, arg) => {
      if (slot.changesMode !== arg.mode) slot.changes = null;
    },
    onFulfilled: (slot, payload, arg) => {
      slot.changes = payload.files;
      slot.changesMode = arg.mode;
    },
  });
  scopedCases(builder, loadCommitDetail, {
    loading: "commitDetailLoading",
    dropFulfilled: staleScope,
    onFulfilled: (slot, payload) => { slot.commitDetail = payload; },
  });
}

function addGitActionCases(builder: Builder): void {
  actionCases(builder, checkoutBranch, "Checkout failed", (state, payload) => {
    writeToSlot(state, payload.sessionId, (slot) => { slot.status = payload.status; });
  });
  actionCases(builder, createBranch, "Failed to create branch", (state, payload) => {
    writeToSlot(state, payload.sessionId, (slot) => { slot.status = payload.status; });
  });
}

export function addGitCases(builder: Builder): void {
  addGitReadCases(builder);
  addGitHistoryCases(builder);
  addGitActionCases(builder);
}
