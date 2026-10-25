import type { ActionReducerMapBuilder } from "@reduxjs/toolkit";
import { setLeftTab } from "@/store/uiSlice";
import { setActiveSession, removeSession } from "@/store/sessionsSlice";
import { activeSlot, ensureSlot, type WorkspaceState } from "@/store/workspace/state";

function resetSessionUi(state: WorkspaceState): void {
  state.actionLoading = false;
  state.actionOutput = null;
  state.error = null;
}

export function addSessionCases(builder: ActionReducerMapBuilder<WorkspaceState>): void {
  builder
    .addCase(setLeftTab, (state) => {
      const slot = activeSlot(state);
      if (slot) slot.selectedDiff = null;
    })
    .addCase(setActiveSession, (state, action) => {
      state.activeSessionId = action.payload;
      // Repo scope is a viewing preference, but not every session has every
      // repo; "app" always exists.
      state.repoScope = "app";
      resetSessionUi(state);
      if (action.payload) {
        const slot = ensureSlot(state, action.payload);
        slot.loading = true;
        slot.branchesLoading = true;
        slot.treeLoading = true;
        slot.logLoading = true;
      }
    })
    .addCase(removeSession.fulfilled, (state, action) => {
      const id = action.payload;
      delete state.bySession[id];
      const idx = state.lruOrder.indexOf(id);
      if (idx !== -1) state.lruOrder.splice(idx, 1);
      if (state.activeSessionId === id) state.activeSessionId = null;
      resetSessionUi(state);
    });
}
