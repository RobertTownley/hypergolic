import { Modal } from "@/shared/components/Modal";
import { EmptyState } from "@/shared/components/EmptyState";
import { Spinner } from "@/shared/components/Spinner";
import { useCommitDetail } from "./useCommitDetail";
import type { DiffRow } from "@/shared/diff";
import styles from "./CommitDetailModal.module.css";

function formatDate(isoDate: string): string {
  return new Date(isoDate).toLocaleString(undefined, {
    month: "short", day: "numeric", year: "numeric",
    hour: "numeric", minute: "2-digit",
  });
}

function CommitTitle({ detail }: { detail: { short_hash: string; message: string; author: string; date: string } | null }) {
  if (!detail) return <span className={styles.headerTitle}>Loading{"\u2026"}</span>;
  return (
    <div className={styles.titleBlock}>
      <div className={styles.headerTop}>
        <span className={styles.hash}>{detail.short_hash}</span>
        <span className={styles.message}>{detail.message}</span>
      </div>
      <div className={styles.headerMeta}>
        <span className={styles.author}>{detail.author}</span>
        <span className={styles.date}>{formatDate(detail.date)}</span>
      </div>
    </div>
  );
}

function DiffLineRow({ line }: { line: DiffRow }) {
  if (line.type === "file-header") {
    return <div className={styles.fileHeader}>{line.content}</div>;
  }
  return (
    <div className={`${styles.diffLine} ${styles[line.type]}`}>
      <span className={styles.lineNumber}>{line.oldNum ?? ""}</span>
      <span className={styles.lineNumber}>{line.newNum ?? ""}</span>
      <span className={styles.lineContent}>{line.content}</span>
    </div>
  );
}

export function CommitDetailModal() {
  const { commitDetail, commitDetailLoading, isOpen, diffLines, onClose } = useCommitDetail();

  if (!isOpen) return null;

  return (
    <Modal
      onClose={onClose}
      title={<CommitTitle detail={commitDetail} />}
      width={800}
      maxHeight="85vh"
      className={styles.commitModal}
    >
      {commitDetailLoading ? (
        <Spinner centered />
      ) : diffLines.length === 0 ? (
        <EmptyState text="No changes in this commit" />
      ) : (
        <div className={styles.diffContent}>
          {diffLines.map((line, i) => (
            <DiffLineRow key={i} line={line} />
          ))}
        </div>
      )}
    </Modal>
  );
}
