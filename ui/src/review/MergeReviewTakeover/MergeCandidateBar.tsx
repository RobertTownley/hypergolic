import type { ReviewView } from "@/api/git";
import type { MergeCandidate } from "@/types/api";
import styles from "./MergeReviewTakeover.module.css";

interface MergeCandidateBarProps {
  merge: MergeCandidate;
  view: ReviewView;
  onViewChange: (view: ReviewView) => void;
}

export function mergeSummary(merge: MergeCandidate): string {
  const n = merge.merged_count;
  const commits = `${n} commit${n === 1 ? "" : "s"} from ${merge.merged_from}`;
  if (merge.conflict_paths.length === 0) {
    return `Clean merge of ${commits}; no conflict resolutions`;
  }
  const files = merge.conflict_paths.length;
  return `Merge of ${commits}; conflicts resolved in ${files} file${files === 1 ? "" : "s"}`;
}

export function MergeCandidateBar({ merge, view, onViewChange }: MergeCandidateBarProps) {
  const showingRange = view === "range";
  return (
    <div className={styles.commitMsgBar} aria-label="Merge candidate">
      <span className={styles.commitMsgLabel}>Merge</span>
      <div className={styles.commitMsgContent}>
        <span className={styles.commitMsgSubject}>{mergeSummary(merge)}</span>
        {showingRange && (
          <span className={styles.mergeViewNote}>
            Showing every change the merge brought in from {merge.merged_from}.
          </span>
        )}
      </div>
      <button
        className={styles.commitMsgToggle}
        onClick={() => onViewChange(showingRange ? "merge" : "range")}
      >
        {showingRange ? "Show conflict resolutions only" : "Show full range diff"}
      </button>
    </div>
  );
}
