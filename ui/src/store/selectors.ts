import { createSelector } from "@reduxjs/toolkit";
import type { RootState } from "@/store";
import type { Session, Message, SessionStatus } from "@/types/api";
import { emptySessionWorkspace, type SessionWorkspace } from "@/store/workspace/state";

const selectProjectEntities = (state: RootState) => state.projects.entities;
export const selectProjectIds = (state: RootState) => state.projects.ids;
export const selectProjectsInitialized = (state: RootState) => state.projects.initialized;
export const selectProjectsLoading = (state: RootState) => state.projects.loading;

export const selectActiveProject = createSelector(
  [
    selectProjectEntities,
    (state: RootState) => state.sessions.entities,
    (state: RootState) => state.sessions.activeSessionId,
  ],
  (projects, sessions, activeSessionId) => {
    if (!activeSessionId) return null;
    const session = sessions[activeSessionId];
    if (!session) return null;
    return projects[session.project_id] ?? null;
  },
);

export const selectActiveProjectId = createSelector(
  [selectActiveProject],
  (project) => project?.id ?? null,
);

export const getProjectId = (state: RootState) => selectActiveProjectId(state) ?? undefined;

export const selectSessionEntities = (state: RootState) => state.sessions.entities;
export const selectSessionIds = (state: RootState) => state.sessions.ids;
export const selectActiveSessionId = (state: RootState) => state.sessions.activeSessionId;
export const selectSessionsInitialized = (state: RootState) => state.sessions.initialized;
export const selectSessionsLoading = (state: RootState) => state.sessions.loading;

export const selectActiveSession = createSelector(
  [selectSessionEntities, selectActiveSessionId],
  (entities, activeId): Session | null => (activeId ? entities[activeId] ?? null : null),
);

const selectAllSessions = createSelector(
  [selectSessionIds, selectSessionEntities],
  (ids, entities) => ids.map((id: string) => entities[id]).filter((s): s is Session => !!s),
);



const selectMessagesBySessionId = (state: RootState) => state.messages.bySessionId;
const selectStreamingBlocksBySessionId = (state: RootState) => state.messages.streamingBlocksBySessionId;
const selectStreamingSessions = (state: RootState) => state.messages.streamingSessions;
const selectPendingApprovals = (state: RootState) => state.messages.pendingApprovalBySession;
const selectMessageErrors = (state: RootState) => state.messages.errorBySessionId;
const selectMessageLoadingStates = (state: RootState) => state.messages.loadingSessionIds;
const selectMessageLoadedStates = (state: RootState) => state.messages.loadedSessionIds;

export const selectMessagesForSession = createSelector(
  [selectMessagesBySessionId, (_state: RootState, sessionId: string) => sessionId],
  (bySessionId, sessionId): Message[] => bySessionId[sessionId] ?? [],
);

export const selectIsSessionStreaming = createSelector(
  [selectStreamingSessions, (_state: RootState, sessionId: string) => sessionId],
  (streamingSessions, sessionId): boolean => !!streamingSessions[sessionId],
);

export const selectStreamingBlocksForSession = createSelector(
  [selectStreamingBlocksBySessionId, (_state: RootState, sessionId: string) => sessionId],
  (blocksBySessionId, sessionId): import("@/store/messagesSlice").StreamingBlock[] =>
    blocksBySessionId[sessionId] ?? [],
);

export const selectPendingApprovalForSession = createSelector(
  [selectPendingApprovals, (_state: RootState, sessionId: string) => sessionId],
  (approvals, sessionId) => approvals[sessionId]?.[0] ?? null,
);

export const selectSessionError = createSelector(
  [selectMessageErrors, (_state: RootState, sessionId: string) => sessionId],
  (errors, sessionId): string | null => errors[sessionId] ?? null,
);

export const selectIsMessagesLoading = createSelector(
  [selectMessageLoadingStates, (_state: RootState, sessionId: string) => sessionId],
  (loadingStates, sessionId): boolean => !!loadingStates[sessionId],
);

export const selectIsMessagesLoaded = createSelector(
  [selectMessageLoadedStates, (_state: RootState, sessionId: string) => sessionId],
  (loadedStates, sessionId): boolean => !!loadedStates[sessionId],
);

const EMPTY_SLOT: SessionWorkspace = emptySessionWorkspace();

export const selectActiveWorkspace = (state: RootState): SessionWorkspace => {
  const id = state.workspace.activeSessionId;
  if (!id) return EMPTY_SLOT;
  return state.workspace.bySession[id] ?? EMPTY_SLOT;
};

export const selectSelectedDiff = (state: RootState) => selectActiveWorkspace(state).selectedDiff;
export const selectDiffLoading = (state: RootState) => selectActiveWorkspace(state).diffLoading;
export const selectChanges = (state: RootState) => selectActiveWorkspace(state).changes;
export const selectChangesLoading = (state: RootState) => selectActiveWorkspace(state).changesLoading;
export const selectGitLogEntries = (state: RootState) => selectActiveWorkspace(state).logEntries;
export const selectGitLogLoading = (state: RootState) => selectActiveWorkspace(state).logLoading;
export const selectCommitDetail = (state: RootState) => selectActiveWorkspace(state).commitDetail;
export const selectCommitDetailLoading = (state: RootState) => selectActiveWorkspace(state).commitDetailLoading;
export const selectFileTreeRoot = (state: RootState) => selectActiveWorkspace(state).root;
export const selectFileTree = (state: RootState) => selectActiveWorkspace(state).tree;
export const selectFileTreeLoading = (state: RootState) => selectActiveWorkspace(state).treeLoading;
export const selectSelectedFilePath = (state: RootState) => selectActiveWorkspace(state).selectedFilePath;
export const selectExpandedFilePaths = (state: RootState) => selectActiveWorkspace(state).expandedFilePaths;
export const selectFileContent = (state: RootState) => selectActiveWorkspace(state).fileContent;
export const selectFileContentLoading = (state: RootState) => selectActiveWorkspace(state).fileContentLoading;
export const selectFileContentError = (state: RootState) => selectActiveWorkspace(state).fileContentError;

export const selectActionOutput = (state: RootState) => state.workspace.actionOutput;
export const selectGitError = (state: RootState) => state.workspace.error;
export const selectDiffMode = (state: RootState) => state.workspace.diffMode;
export const selectRepoScope = (state: RootState) => state.workspace.repoScope;
export const selectAvailableRepos = (state: RootState) =>
  selectActiveWorkspace(state).availableRepos;
export const selectFileSource = (state: RootState) => state.workspace.fileSource;

export const selectSandboxContainers = (state: RootState) => selectActiveWorkspace(state).sandboxContainers;
export const selectSandboxContainersLoaded = (state: RootState) => selectActiveWorkspace(state).sandboxContainersLoaded;
export const selectSandboxContainer = (state: RootState) => selectActiveWorkspace(state).sandboxContainer;
export const selectSandboxRoot = (state: RootState) => selectActiveWorkspace(state).sandboxRoot;
export const selectSandboxDirCache = (state: RootState) => selectActiveWorkspace(state).sandboxDirCache;
export const selectSandboxExpandedPaths = (state: RootState) => selectActiveWorkspace(state).sandboxExpandedPaths;
export const selectSandboxSelectedPath = (state: RootState) => selectActiveWorkspace(state).sandboxSelectedPath;
export const selectSandboxContent = (state: RootState) => selectActiveWorkspace(state).sandboxContent;
export const selectSandboxLoading = (state: RootState) => selectActiveWorkspace(state).sandboxLoading;
export const selectSandboxContentLoading = (state: RootState) => selectActiveWorkspace(state).sandboxContentLoading;
export const selectSandboxError = (state: RootState) => selectActiveWorkspace(state).sandboxError;
export const selectSandboxStarting = (state: RootState) => selectActiveWorkspace(state).sandboxStarting;
export const selectSandboxContentError = (state: RootState) => selectActiveWorkspace(state).sandboxContentError;






const TERMINAL_STATUSES: Set<SessionStatus> = new Set(["concluding", "concluded", "interrupted"]);

const JUMP_PRIORITY: Record<SessionStatus, number> = {
  awaiting_approval: 1,
  idle: 2,
  interrupted: 2,
  error: 3,
  thinking: 4,
  streaming: 4,
  retrying: 4,
  tool_use: 4,
  truncating: 4,
  concluding: 5,
  concluded: 5,
};

export function rankJumpCandidates(sessions: Session[]): Session[] {
  return sessions
    .filter((s) => !TERMINAL_STATUSES.has(s.status))
    .sort((a, b) => {
      const tierDiff = JUMP_PRIORITY[a.status] - JUMP_PRIORITY[b.status];
      if (tierDiff !== 0) return tierDiff;
      // Prefer top-level sessions over dispatch children within a tier.
      const childDiff = Number(!!a.parent_id) - Number(!!b.parent_id);
      if (childDiff !== 0) return childDiff;
      return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
    });
}

export const selectJumpToSessionId = createSelector(
  [selectAllSessions, selectActiveSessionId],
  (sessions, activeSessionId): string | null => {
    const sorted = rankJumpCandidates(sessions);
    if (sorted.length === 0) return null;
    if (sorted[0].id === activeSessionId) return sorted[1]?.id ?? null;
    return sorted[0].id;
  },
);
