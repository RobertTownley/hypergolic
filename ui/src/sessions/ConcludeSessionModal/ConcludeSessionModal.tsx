import React, { useState, useCallback, useEffect } from "react";
import { CircleCheckIcon, TriangleAlertIcon } from "lucide-react";
import { Modal } from "@/shared/components/Modal";
import { useAppDispatch, useAppSelector } from "@/store";
import { selectConcludeDraft, setConcludeDraft } from "@/store/uiSlice";
import { fetchConcludePreview } from "@/api/sessions";
import type { ConcludePreview } from "@/types/api";
import styles from "./ConcludeSessionModal.module.css";

const RATING_LABELS = [
  { value: 1, label: "Poor" },
  { value: 2, label: "Below Average" },
  { value: 3, label: "Neutral" },
  { value: 4, label: "Good" },
  { value: 5, label: "Excellent" },
];

interface ConcludeSessionModalProps {
  onClose: () => void;
  onConclude: (
    rating: number,
    feedback: string,
    deleteWorktree: boolean,
    deleteBranch: boolean,
    analyzeLearnings: boolean,
  ) => void;
  sessionId: string;
  errorDetail?: string | null;
}

export function ConcludeSessionModal({
  onClose,
  onConclude,
  sessionId,
  errorDetail,
}: ConcludeSessionModalProps) {
  const dispatch = useAppDispatch();
  // The draft lives in the store (not local state) because the modal
  // unmounts before the server can reject a conclude; on re-open it must
  // restore the rating/feedback/flags the user already picked. Cleared
  // only on a server-confirmed conclude (see uiSlice).
  const { rating, feedback, deleteWorktree, deleteBranch, analyzeLearnings } = useAppSelector(
    (s) => selectConcludeDraft(s, sessionId),
  );
  const [preview, setPreview] = useState<ConcludePreview | null>(null);

  const setRating = useCallback(
    (value: number) => dispatch(setConcludeDraft({ sessionId, rating: value })),
    [dispatch, sessionId],
  );

  const toggleAnalyze = useCallback(
    () => dispatch(setConcludeDraft({ sessionId, analyzeLearnings: !analyzeLearnings })),
    [dispatch, sessionId, analyzeLearnings],
  );

  useEffect(() => {
    let cancelled = false;
    fetchConcludePreview(sessionId)
      .then((p) => { if (!cancelled) setPreview(p); })
      .catch(() => { if (!cancelled) setPreview(null); });
    return () => { cancelled = true; };
  }, [sessionId]);

  const submit = useCallback(() => {
    onConclude(rating, feedback, deleteWorktree, deleteBranch, analyzeLearnings);
  }, [onConclude, rating, feedback, deleteWorktree, deleteBranch, analyzeLearnings]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Enter" && !(e.target instanceof HTMLTextAreaElement)) {
        e.preventDefault();
        e.stopPropagation();
        submit();
        return;
      }
      if (e.key >= "1" && e.key <= "5" && !(e.target instanceof HTMLTextAreaElement)) {
        e.preventDefault();
        setRating(parseInt(e.key, 10));
        return;
      }
      if (e.key.toLowerCase() === "a" && !e.metaKey && !e.ctrlKey && !(e.target instanceof HTMLTextAreaElement)) {
        e.preventDefault();
        toggleAnalyze();
      }
    };
    document.addEventListener("keydown", handler, true);
    return () => document.removeEventListener("keydown", handler, true);
  }, [submit, setRating, toggleAnalyze]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !(e.target instanceof HTMLTextAreaElement)) {
        e.preventDefault();
        e.stopPropagation();
        return;
      }
      if (e.key >= "1" && e.key <= "5" && !(e.target instanceof HTMLTextAreaElement)) {
        e.preventDefault();
        e.stopPropagation();
        return;
      }
      if (e.key.toLowerCase() === "a" && !e.metaKey && !e.ctrlKey && !(e.target instanceof HTMLTextAreaElement)) {
        e.preventDefault();
        e.stopPropagation();
        return;
      }
    },
    [],
  );

  const isWorktree = preview?.is_worktree_session ?? false;
  const hasUnmerged = preview?.branch_has_unmerged_commits ?? false;
  const unmergedCount = preview?.unmerged_count ?? 0;

  return (
    <Modal
      onClose={onClose}
      onKeyDown={handleKeyDown}
      title="Conclude Session"
      icon={<CircleCheckIcon />}
      width={520}
      footer={
        <div className={styles.footerRow}>
          <span className={styles.hint}>
            Press <kbd className={styles.kbd}>Enter</kbd> to conclude
          </span>
          <button className={styles.concludeBtn} onClick={submit}>
            Conclude
          </button>
        </div>
      }
    >
      <div className={styles.body}>
        {errorDetail && (
          <div className={styles.errorBox} data-testid="conclude-error">
            <TriangleAlertIcon className={styles.errorIcon} />
            <div className={styles.errorText}>{errorDetail}</div>
          </div>
        )}
        <div className={styles.section}>
          <label className={styles.label}>Rating</label>
          <div className={styles.ratingRow}>
            {RATING_LABELS.map((item) => (
              <button
                key={item.value}
                className={`${styles.ratingBtn} ${item.value === rating ? styles.ratingActive : ""}`}
                onClick={() => setRating(item.value)}
                data-testid={`rating-${item.value}`}
              >
                <kbd className={styles.kbd}>{item.value}</kbd>
                <span className={styles.ratingLabel}>{item.label}</span>
              </button>
            ))}
          </div>
        </div>
        <div className={styles.section}>
          <label className={styles.label}>Feedback</label>
          <textarea
            className={styles.textarea}
            value={feedback}
            onChange={(e) => dispatch(setConcludeDraft({ sessionId, feedback: e.target.value }))}
            placeholder="Session feedback (optional)"
            rows={3}
            data-testid="feedback-textarea"
          />
        </div>
        <div className={styles.section}>
          <label className={styles.checkboxRow}>
            <input type="checkbox" checked={analyzeLearnings} onChange={(e) => dispatch(setConcludeDraft({ sessionId, analyzeLearnings: e.target.checked }))} data-testid="analyze-learnings-checkbox" />
            <span className={styles.checkboxLabel}>
              <kbd className={styles.kbd}>A</kbd>&nbsp;Analyze session learnings (runs a summarization session)
            </span>
          </label>
        </div>
        {isWorktree && (
          <div className={styles.section}>
            <label className={styles.label}>Worktree</label>
            <div className={styles.checkboxList}>
              <label className={styles.checkboxRow}>
                <input type="checkbox" checked={deleteWorktree} onChange={(e) => dispatch(setConcludeDraft({ sessionId, deleteWorktree: e.target.checked }))} data-testid="delete-worktree-checkbox" />
                <span className={styles.checkboxLabel}>Delete worktree directory</span>
              </label>
              <label className={styles.checkboxRow}>
                <input type="checkbox" checked={deleteBranch} onChange={(e) => dispatch(setConcludeDraft({ sessionId, deleteBranch: e.target.checked }))} data-testid="delete-branch-checkbox" />
                <span className={styles.checkboxLabel}>
                  Delete session branch
                  {hasUnmerged && (
                    <span className={styles.inlineWarn}>&nbsp;({unmergedCount} unmerged commit{unmergedCount === 1 ? "" : "s"})</span>
                  )}
                </span>
              </label>
            </div>
            {deleteBranch && hasUnmerged && (
              <div className={styles.warning} data-testid="unmerged-warning">
                <TriangleAlertIcon className={styles.warnIcon} />
                <div>
                  <div className={styles.warnTitle}>Branch has {unmergedCount} commit{unmergedCount === 1 ? "" : "s"} not yet merged</div>
                  <div className={styles.warnDetail}>Deleting the branch will discard them. Uncheck &ldquo;Delete branch&rdquo; to keep the work for later review.</div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}
