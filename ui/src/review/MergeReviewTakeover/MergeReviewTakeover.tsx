import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeftIcon, BanIcon, CheckIcon } from "lucide-react";
import { Spinner } from "@/shared/components";
import { DiffTotals, FileItemRow, TreeSection } from "@/git/FileTree";
import type { PendingApproval } from "@/store/messagesSlice";
import { useMergeReview } from "./useMergeReview";
import { ReviewDiff } from "./ReviewDiff";
import { MergeCandidateBar } from "./MergeCandidateBar";
import { MergeDescription } from "./MergeDescription";
import styles from "./MergeReviewTakeover.module.css";

interface MergeReviewTakeoverProps {
  sessionId: string;
  approval: PendingApproval | null;
}

function splitMessage(message: string | null): [string | null, string | null] {
  if (!message) return [null, null];
  const [subject, ...rest] = message.split("\n");
  const body = rest.join("\n").trim();
  return [subject, body || null];
}

function approvalLabel(approval: PendingApproval): string {
  const branch = (approval.toolInput?.arguments as { branch?: string } | undefined)?.branch;
  return branch ? `Merge into ${branch}` : "Merge approval requested";
}

function statusLabel(status: string): string {
  switch (status) {
    case "A": return "added";
    case "D": return "deleted";
    case "R": return "renamed";
    default: return "modified";
  }
}

export function MergeReviewTakeover({ sessionId, approval }: MergeReviewTakeoverProps) {
  const {
    review,
    view,
    setView,
    repoScope,
    loading,
    error,
    files,
    fileTree,
    expandedDirs,
    toggleDir,
    selectedPath,
    selectedFile,
    viewed,
    viewedCount,
    comments,
    diffMode,
    overallNote,
    setOverallNote,
    selectFile,
    stepFile,
    handleToggleViewed,
    handleSetDiffMode,
    handleAddComment,
    handleRemoveComment,
    handleClose,
    handleApprove,
    handleRequestChanges,
  } = useMergeReview(sessionId, approval);

  const diffAreaRef = useRef<HTMLDivElement>(null);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "j") { e.preventDefault(); stepFile(1); }
      else if (e.key === "k") { e.preventDefault(); stepFile(-1); }
      else if (e.key === "v" && selectedPath) {
        e.preventDefault();
        handleToggleViewed(selectedPath);
        stepFile(1);
      } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        const el = diffAreaRef.current;
        if (el) {
          e.preventDefault();
          el.scrollBy({ top: e.key === "ArrowDown" ? 120 : -120 });
        }
      } else if (e.key === "Escape") {
        e.preventDefault();
        handleClose();
      }
    },
    [stepFile, selectedPath, handleToggleViewed, handleClose],
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  const totalAdds = files.reduce((n, f) => n + f.additions, 0);
  const totalDels = files.reduce((n, f) => n + f.deletions, 0);
  const commitMessage = (approval?.toolInput?.commit_message as string) ?? null;
  const [msgSubject, msgBody] = splitMessage(commitMessage);
  const [msgExpanded, setMsgExpanded] = useState(false);
  const description = ((approval?.toolInput?.description as string) ?? "").trim();

  return (
    <div className={styles.root} aria-label="Merge review">
      <div className={styles.topbar}>
        <button className={styles.backBtn} onClick={handleClose}>
          <ArrowLeftIcon /> Back to session
        </button>
        <span className={styles.pillWarn}>
          {approval ? approvalLabel(approval) : "Reviewing vs base"}
        </span>
        {repoScope === "harness" && (
          <span className={styles.branchChip}>harness repo</span>
        )}
        {review && (
          <span className={styles.branchFlow}>
            <span className={styles.branchChip}>{review.branch}</span>
            <span className={styles.arrow}>→</span>
            <span className={styles.branchChip}>{review.base_branch}</span>
          </span>
        )}
        <div className={styles.spacer} />
        {review && (
          <span className={styles.stats}>
            <span className={styles.add}>+{totalAdds}</span>{" "}
            <span className={styles.del}>−{totalDels}</span> · {files.length} files ·{" "}
            {review.commits.length} commits
          </span>
        )}
        <div className={styles.modeToggle}>
          <button
            className={diffMode === "unified" ? styles.modeOn : styles.modeOff}
            onClick={() => handleSetDiffMode("unified")}
          >
            Unified
          </button>
          <button
            className={diffMode === "split" ? styles.modeOn : styles.modeOff}
            onClick={() => handleSetDiffMode("split")}
          >
            Split
          </button>
        </div>
      </div>

      {msgSubject && (
        <div className={styles.commitMsgBar}>
          <span className={styles.commitMsgLabel}>Merge commit</span>
          <div className={styles.commitMsgContent}>
            <span className={styles.commitMsgSubject}>{msgSubject}</span>
            {msgExpanded && msgBody && (
              <pre className={styles.commitMsgBody}>{msgBody}</pre>
            )}
          </div>
          {msgBody && (
            <button
              className={styles.commitMsgToggle}
              onClick={() => setMsgExpanded((v) => !v)}
            >
              {msgExpanded ? "Hide full message" : "Show full message"}
            </button>
          )}
        </div>
      )}

      {description && <MergeDescription text={description} />}

      {review?.merge && (
        <MergeCandidateBar merge={review.merge} view={view} onViewChange={setView} />
      )}

      <div className={styles.main}>
        <div className={styles.fileRail}>
          <div className={styles.railHead}>
            <span>Files changed</span>
            <span>
              {files.length}
              <DiffTotals files={files} />
            </span>
          </div>
          <div className={styles.fileList}>
            <TreeSection
              tree={fileTree}
              depth={0}
              expandedDirs={expandedDirs}
              toggleDir={toggleDir}
              renderFile={(node, depth) => {
                const f = node.file;
                if (!f) return null;
                return (
                  <FileItemRow
                    key={f.path}
                    file={f}
                    depth={depth}
                    selected={f.path === selectedPath}
                    onSelect={() => selectFile(f.path)}
                    actions={null}
                    leading={
                      <span
                        className={`${styles.viewedDot} ${viewed[f.path] ? styles.viewedDotOn : ""}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleToggleViewed(f.path);
                        }}
                        title="Toggle viewed"
                      />
                    }
                  />
                );
              }}
            />
          </div>
          <div className={styles.railFoot}>
            {viewedCount} of {files.length} files viewed
            <div className={styles.progress}>
              <i style={{ width: files.length ? `${(viewedCount / files.length) * 100}%` : 0 }} />
            </div>
          </div>
        </div>

        <div className={styles.diffArea} ref={diffAreaRef} tabIndex={-1}>
          {loading && (
            <div className={styles.centered}><Spinner size="large" /></div>
          )}
          {!loading && error && <div className={styles.centered}>{error}</div>}
          {!loading && !error && files.length === 0 && (
            <div className={styles.centered}>
              {review?.merge
                ? "No conflict resolutions to review"
                : `No changes vs ${review?.base_branch ?? "base"}`}
            </div>
          )}
          {!loading && selectedFile && (
            <>
              <div className={styles.fileHead}>
                <span className={styles.fileHeadPath}>
                  {selectedFile.old_path ? `${selectedFile.old_path} → ` : ""}
                  {selectedFile.path}
                </span>
                <span className={styles.statusPill}>{statusLabel(selectedFile.status)}</span>
                <span className={styles.fileHeadRight}>
                  <label className={styles.viewedLabel}>
                    <input
                      type="checkbox"
                      checked={!!viewed[selectedFile.path]}
                      onChange={() => handleToggleViewed(selectedFile.path)}
                    />
                    Viewed
                  </label>
                  <span className={styles.kbdHint}>j/k files · v viewed+next · ↑/↓ scroll · click line to comment</span>
                </span>
              </div>
              <ReviewDiff
                file={selectedFile}
                mode={diffMode}
                comments={comments}
                onAddComment={handleAddComment}
                onRemoveComment={handleRemoveComment}
              />
            </>
          )}
        </div>
      </div>

      {approval && (
        <div className={styles.actionBar}>
          <span className={styles.commentCount}>
            {comments.length > 0 &&
              `${comments.length} inline comment${comments.length === 1 ? "" : "s"} queued`}
          </span>
          <input
            className={styles.overallInput}
            value={overallNote}
            onChange={(e) => setOverallNote(e.target.value)}
            placeholder="Overall feedback (optional) — inline comments will be attached…"
          />
          <div className={styles.spacer} />
          <button className={styles.dangerBtn} onClick={handleRequestChanges}>
            <BanIcon /> Request changes
          </button>
          <button className={styles.approveBtn} onClick={handleApprove}>
            <CheckIcon /> Approve merge
          </button>
        </div>
      )}
    </div>
  );
}
