import { FileDiffIcon, GitBranchIcon, RotateCwIcon } from "lucide-react";
import type { GitStatusResponse, DiffMode, RepoScope } from "@/types/api";
import { PanelHeader } from "@/shared/components/Panel";
import { IconButton, BranchSelect } from "@/shared/components";
import styles from "./VersionControl.module.css";

export function BranchHeader({
  status,
  onRefresh,
  onOpenReview,
  branches,
  onCheckout,
  onCreateBranch,
  checkoutLoading,
  diffMode,
  onSetDiffMode,
  showDiffModeToggle,
  repoScope,
  onSetRepoScope,
  availableRepos,
}: {
  status: GitStatusResponse | null;
  onRefresh: () => void;
  onOpenReview?: () => void;
  branches: string[];
  onCheckout: (branch: string) => void;
  onCreateBranch: (name: string) => void;
  checkoutLoading: boolean;
  diffMode: DiffMode;
  onSetDiffMode: (mode: DiffMode) => void;
  showDiffModeToggle: boolean;
  repoScope: RepoScope;
  onSetRepoScope: (scope: RepoScope) => void;
  availableRepos: Record<RepoScope, boolean> | null;
}) {
  const repoOptions: { scope: RepoScope; label: string }[] = [
    { scope: "app", label: "App" },
    { scope: "harness", label: "Harness" },
    { scope: "shared", label: "Shared" },
  ];
  const actions = (
    <>
      {onOpenReview && (
        <IconButton
          size="medium"
          icon={<FileDiffIcon />}
          onClick={onOpenReview}
          title="Review vs base"
        />
      )}
      <IconButton size="medium" icon={<RotateCwIcon />} onClick={onRefresh} />
    </>
  );

  return (
    <>
      <PanelHeader icon={<GitBranchIcon />} actions={status ? actions : undefined}>
        Source Control
      </PanelHeader>

      {status && (
        <div className={styles.repoToggle} role="tablist">
          {repoOptions.map(({ scope, label }) => {
            const enabled = scope === "app" || !!availableRepos?.[scope];
            return (
              <button
                key={scope}
                type="button"
                role="tab"
                aria-selected={repoScope === scope}
                disabled={!enabled}
                title={enabled ? undefined : `This session has no ${scope} repo`}
                className={
                  !enabled
                    ? styles.diffModeDisabled
                    : repoScope === scope
                      ? styles.diffModeActive
                      : styles.diffModeBtn
                }
                onClick={() => onSetRepoScope(scope)}
              >
                {label}
              </button>
            );
          })}
        </div>
      )}

      {status && showDiffModeToggle && (
        <div className={styles.diffModeToggle} role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={diffMode === "all"}
            className={diffMode === "all" ? styles.diffModeActive : styles.diffModeBtn}
            onClick={() => onSetDiffMode("all")}
          >
            All changes
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={diffMode === "uncommitted"}
            className={diffMode === "uncommitted" ? styles.diffModeActive : styles.diffModeBtn}
            onClick={() => onSetDiffMode("uncommitted")}
          >
            Uncommitted
          </button>
        </div>
      )}

      {status && (
        <div className={styles.branchRow}>
          {repoScope === "app" ? (
            <BranchSelect
              branches={branches}
              value={status.branch}
              onSelect={onCheckout}
              onCreate={onCreateBranch}
              loading={checkoutLoading}
              inline
            />
          ) : (
            <span className={styles.branchName}>{status.branch}</span>
          )}

          {(status.ahead > 0 || status.behind > 0) && (
            <span className={styles.aheadBehind}>
              {status.ahead > 0 && (
                <span className={styles.ahead}>↑{status.ahead}</span>
              )}
              {status.ahead > 0 && status.behind > 0 && " "}
              {status.behind > 0 && (
                <span className={styles.behind}>↓{status.behind}</span>
              )}
            </span>
          )}
        </div>
      )}
    </>
  );
}
