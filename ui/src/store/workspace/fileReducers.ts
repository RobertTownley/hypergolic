import type { PayloadAction } from "@reduxjs/toolkit";
import {
  activeSlot,
  resetSandboxBrowse,
  type FileSource,
  type WorkspaceState,
} from "@/store/workspace/state";

export const fileReducers = {
  selectFile(state: WorkspaceState, action: PayloadAction<string | null>) {
    const slot = activeSlot(state);
    if (!slot) return;
    slot.selectedFilePath = action.payload;
    if (!action.payload) {
      slot.fileContent = null;
      slot.fileContentError = null;
    }
  },
  setExpandedFilePaths(state: WorkspaceState, action: PayloadAction<string[]>) {
    const slot = activeSlot(state);
    if (slot) slot.expandedFilePaths = action.payload;
  },
  setFileSource(state: WorkspaceState, action: PayloadAction<FileSource>) {
    state.fileSource = action.payload;
  },
};

export const sandboxReducers = {
  setSandboxContainer(state: WorkspaceState, action: PayloadAction<string | null>) {
    const slot = activeSlot(state);
    if (!slot) return;
    slot.sandboxContainer = action.payload;
    const container = slot.sandboxContainers.find((c) => c.id === action.payload);
    slot.sandboxRoot = container?.roots[0]?.id ?? null;
    resetSandboxBrowse(slot);
  },
  setSandboxRoot(state: WorkspaceState, action: PayloadAction<string | null>) {
    const slot = activeSlot(state);
    if (!slot) return;
    slot.sandboxRoot = action.payload;
    resetSandboxBrowse(slot);
  },
  selectSandboxFile(state: WorkspaceState, action: PayloadAction<string | null>) {
    const slot = activeSlot(state);
    if (!slot) return;
    slot.sandboxSelectedPath = action.payload;
    if (!action.payload) {
      slot.sandboxContent = null;
      slot.sandboxContentError = null;
    }
  },
  setSandboxExpandedPaths(state: WorkspaceState, action: PayloadAction<string[]>) {
    const slot = activeSlot(state);
    if (slot) slot.sandboxExpandedPaths = action.payload;
  },
  refreshSandbox(state: WorkspaceState) {
    const slot = activeSlot(state);
    if (!slot) return;
    // Drop cached listings/content so the explorer re-fetches the live state.
    slot.sandboxDirCache = {};
    slot.sandboxContent = null;
    slot.sandboxContentError = null;
    slot.sandboxError = null;
    if (slot.sandboxSelectedPath) {
      slot.sandboxExpandedPaths = slot.sandboxExpandedPaths.slice();
    }
  },
};
