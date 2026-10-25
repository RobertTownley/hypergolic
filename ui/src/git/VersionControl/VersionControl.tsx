import { FaceSlightlySmilingIcon } from "lucide-react";
import { useAppSelector } from "@/store";
import { selectActiveSessionId, selectActiveSession } from "@/store/selectors";
import { openReview } from "@/store/reviewSlice";
import { clearError } from "@/store/workspaceSlice";
import { loadDiff, stageFiles, unstageFiles, discardFiles } from "@/store/workspaceThunks";
import { EmptyState } from "@/shared/components/EmptyState";
import { Panel, PanelBody } from "@/shared/components/Panel";
import { Spinner } from "@/shared/components/Spinner";
import { BranchHeader } from "./BranchHeader";
import { StagedSection } from "./StagedSection";
import { ChangesSection } from "./ChangesSection";
import { AllChangesSection } from "./AllChangesSection";
import { StatusMessages } from "./StatusMessages";
import { useVersionControl } from "./useVersionControl";
import styles from "./VersionControl.module.css";

export function VersionControl() {
  const {
    status,
    loading,
    actionOutput,
    error,
    expandedDirs,
    toggleDir,
    refresh,
    stagedTree,
    unstagedTree,
    allChangesTree,
    hasStagedFiles,
    hasUnstagedFiles,
    hasUntracked,
    hasUncommittedChanges,
    hasAllChanges,
    diffMode,
    onSetDiffMode,
    repoScope,
    onSetRepoScope,
    availableRepos,
    branches,
    checkoutLoading,
    handleCheckout,
    handleCreateBranch,
    dispatch,
  } = useVersionControl();
  const activeSessionId = useAppSelector(selectActiveSessionId);
  const activeSession = useAppSelector(selectActiveSession);
  const baseBranch = activeSession?.base_branch ?? null;
  // "All changes" needs a base branch: the app worktree's for app scope, the
  // harness's own for harness scope; /shared has none.
  const showDiffModeToggle =
    repoScope === "harness" || (repoScope === "app" && !!baseBranch);
  const effectiveMode = showDiffModeToggle ? diffMode : "uncommitted";
  const hasAnyChanges = effectiveMode === "all" ? hasAllChanges : hasUncommittedChanges;

  return (
    <Panel>
      <BranchHeader
        status={status}
        onRefresh={refresh}
        onOpenReview={
          repoScope === "app" && baseBranch && activeSessionId
            ? () => dispatch(openReview({ sessionId: activeSessionId }))
            : undefined
        }
        branches={branches}
        onCheckout={handleCheckout}
        onCreateBranch={handleCreateBranch}
        checkoutLoading={checkoutLoading}
        diffMode={diffMode}
        onSetDiffMode={onSetDiffMode}
        showDiffModeToggle={showDiffModeToggle}
        repoScope={repoScope}
        onSetRepoScope={onSetRepoScope}
        availableRepos={availableRepos}
      />

      <PanelBody scrollable className={styles.fileList}>
        {loading && !status ? (
          <Spinner centered />
        ) : !hasAnyChanges ? (
          <EmptyState
            icon={<FaceSlightlySmilingIcon />}
            text={effectiveMode === "all" ? "No changes vs base branch" : "Working tree clean"}
          />
        ) : effectiveMode === "all" ? (
          allChangesTree && (
            <AllChangesSection
              allChanges={status!.all_changes}
              allChangesTree={allChangesTree}
              baseBranch={baseBranch}
              expandedDirs={expandedDirs}
              toggleDir={toggleDir}
              onSelectFile={(path) => {
                if (activeSessionId) dispatch(loadDiff({ sessionId: activeSessionId, path, staged: false }));
              }}
            />
          )
        ) : (
          <>
            {hasStagedFiles && stagedTree && (
              <StagedSection
                stagedFiles={status!.staged}
                stagedTree={stagedTree}
                expandedDirs={expandedDirs}
                toggleDir={toggleDir}
                onSelectFile={(path) => {
                  if (activeSessionId) dispatch(loadDiff({ sessionId: activeSessionId, path, staged: true }));
                }}
                onUnstageFile={(path) => {
                  if (activeSessionId) dispatch(unstageFiles({ sessionId: activeSessionId, paths: [path] }));
                }}
                onUnstageAll={() => {
                  if (activeSessionId) dispatch(unstageFiles({ sessionId: activeSessionId, paths: status!.staged.map((f) => f.path) }));
                }}
              />
            )}

            {(hasUnstagedFiles || hasUntracked) && unstagedTree && (
              <ChangesSection
                unstagedFiles={status!.unstaged}
                untrackedFiles={status!.untracked}
                unstagedTree={unstagedTree}
                expandedDirs={expandedDirs}
                toggleDir={toggleDir}
                onSelectFile={(path) => {
                  if (activeSessionId) dispatch(loadDiff({ sessionId: activeSessionId, path, staged: false }));
                }}
                onStageFile={(path) => {
                  if (activeSessionId) dispatch(stageFiles({ sessionId: activeSessionId, paths: [path] }));
                }}
                onDiscardFile={(path) => {
                  if (activeSessionId) dispatch(discardFiles({ sessionId: activeSessionId, paths: [path] }));
                }}
                onStageAll={(paths) => {
                  if (activeSessionId) dispatch(stageFiles({ sessionId: activeSessionId, paths }));
                }}
                onDiscardAll={() => {
                  if (activeSessionId) dispatch(discardFiles({ sessionId: activeSessionId, paths: status!.unstaged.map((f) => f.path) }));
                }}
              />
            )}
          </>
        )}
      </PanelBody>

      <StatusMessages
        error={error}
        actionOutput={actionOutput}
        onDismissError={() => dispatch(clearError())}
      />

    </Panel>
  );
}
