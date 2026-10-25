import type { ActionReducerMapBuilder } from "@reduxjs/toolkit";
import { SANDBOX_STARTING } from "@/api/files";
import { resetSandboxBrowse, type WorkspaceState } from "@/store/workspace/state";
import { scopedCases } from "@/store/workspace/cases";
import {
  loadFileTree,
  loadFileContent,
  loadSandboxContainers,
  loadSandboxDir,
  loadSandboxContent,
} from "@/store/workspaceThunks";

type Builder = ActionReducerMapBuilder<WorkspaceState>;

function addHostFileCases(builder: Builder): void {
  scopedCases(builder, loadFileTree, {
    loading: "treeLoading",
    error: ["treeError", "Failed to load file tree"],
    onFulfilled: (slot, payload) => {
      slot.root = payload.root;
      slot.tree = payload.tree;
    },
  });
  scopedCases(builder, loadFileContent, {
    loading: "fileContentLoading",
    error: ["fileContentError", "Failed to read file"],
    onFulfilled: (slot, payload) => { slot.fileContent = payload; },
  });
}

function addSandboxContainerCases(builder: Builder): void {
  scopedCases(builder, loadSandboxContainers, {
    loading: "sandboxLoading",
    fulfilledId: "arg",
    error: ["sandboxError", "Failed to load sandbox containers"],
    onFulfilled: (slot, payload) => {
      slot.sandboxContainersLoaded = true;
      slot.sandboxContainers = payload.containers;
      // Default selection: first container, its first root.
      if (!slot.sandboxContainer || !slot.sandboxContainers.some((c) => c.id === slot.sandboxContainer)) {
        const first = payload.containers[0] ?? null;
        slot.sandboxContainer = first?.id ?? null;
        slot.sandboxRoot = first?.roots[0]?.id ?? null;
        resetSandboxBrowse(slot);
      }
    },
    onRejected: (slot, error) => {
      slot.sandboxContainersLoaded = true;
      slot.sandboxError = error.message ?? "Failed to load sandbox containers";
    },
  });
}

function addSandboxDirCases(builder: Builder): void {
  scopedCases(builder, loadSandboxDir, {
    loading: "sandboxLoading",
    fulfilledId: "arg",
    error: ["sandboxError", "Failed to list directory"],
    onFulfilled: (slot, payload, arg) => {
      slot.sandboxStarting = false;
      // Ignore responses for a container/root the user has since switched away from.
      if (payload.container !== slot.sandboxContainer || arg.rootId !== slot.sandboxRoot) return;
      slot.sandboxDirCache[payload.path ?? ""] = payload.nodes;
    },
    onRejected: (slot, error) => {
      if (error.name === SANDBOX_STARTING) {
        slot.sandboxStarting = true;
        return;
      }
      slot.sandboxStarting = false;
      slot.sandboxError = error.message ?? "Failed to list directory";
    },
  });
}

function addSandboxContentCases(builder: Builder): void {
  scopedCases(builder, loadSandboxContent, {
    loading: "sandboxContentLoading",
    fulfilledId: "arg",
    error: ["sandboxContentError", "Failed to read file"],
    onFulfilled: (slot, payload) => { slot.sandboxContent = payload; },
    onRejected: (slot, error) => {
      // A file clicked mid-startup is the same "not yet", not a failure.
      slot.sandboxContentError =
        error.name === SANDBOX_STARTING
          ? "Sandbox is starting…"
          : error.message ?? "Failed to read file";
    },
  });
}

export function addFileCases(builder: Builder): void {
  addHostFileCases(builder);
  addSandboxContainerCases(builder);
  addSandboxDirCases(builder);
  addSandboxContentCases(builder);
}
