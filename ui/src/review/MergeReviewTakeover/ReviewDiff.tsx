import { useMemo, useState } from "react";
import type { GitReviewFile } from "@/types/api";
import type { ReviewComment } from "@/store/reviewSlice";
import { parseDiff, toSplitRows, type DiffRow } from "@/shared/diff";
import styles from "./MergeReviewTakeover.module.css";

interface ReviewDiffProps {
  file: GitReviewFile;
  mode: "unified" | "split";
  comments: ReviewComment[];
  onAddComment: (comment: Omit<ReviewComment, "id">) => void;
  onRemoveComment: (commentId: string) => void;
}

interface EditorTarget {
  line: number;
  side: "old" | "new";
}

function rowKey(row: DiffRow): EditorTarget | null {
  if (row.type === "add" || row.type === "context") {
    return row.newNum !== null ? { line: row.newNum, side: "new" } : null;
  }
  if (row.type === "del") {
    return row.oldNum !== null ? { line: row.oldNum, side: "old" } : null;
  }
  return null;
}

function CommentEditor({
  onSave,
  onCancel,
}: {
  onSave: (text: string) => void;
  onCancel: () => void;
}) {
  const [text, setText] = useState("");
  return (
    <div className={styles.commentEditor}>
      <textarea
        className={styles.commentTextarea}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Comment for the agent…"
        autoFocus
        rows={2}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && text.trim()) {
            e.preventDefault();
            onSave(text.trim());
          }
          if (e.key === "Escape") {
            e.preventDefault();
            onCancel();
          }
        }}
      />
      <div className={styles.commentEditorActions}>
        <button className={styles.smallBtn} onClick={onCancel}>Cancel</button>
        <button
          className={`${styles.smallBtn} ${styles.smallBtnPrimary}`}
          disabled={!text.trim()}
          onClick={() => text.trim() && onSave(text.trim())}
        >
          Add comment
        </button>
      </div>
    </div>
  );
}

function CommentCard({
  comment,
  onRemove,
}: {
  comment: ReviewComment;
  onRemove: () => void;
}) {
  return (
    <div className={styles.commentCard}>
      <div className={styles.commentCardHeader}>
        <span className={styles.commentLoc}>
          {comment.path}:{comment.line}
          {comment.side === "old" ? " (removed)" : ""}
        </span>
        <button className={styles.commentDelete} onClick={onRemove} title="Delete comment">✕</button>
      </div>
      <div className={styles.commentText}>{comment.text}</div>
    </div>
  );
}

export function ReviewDiff({ file, mode, comments, onAddComment, onRemoveComment }: ReviewDiffProps) {
  const rows = useMemo(() => parseDiff(file.patch), [file.patch]);
  const splitRows = useMemo(() => (mode === "split" ? toSplitRows(rows) : []), [mode, rows]);
  const [editing, setEditing] = useState<EditorTarget | null>(null);

  const commentsAt = (target: EditorTarget | null) =>
    target
      ? comments.filter((c) => c.path === file.path && c.line === target.line && c.side === target.side)
      : [];

  const attachments = (row: DiffRow) => {
    const target = rowKey(row);
    if (!target) return null;
    const rowComments = commentsAt(target);
    const isEditing = editing !== null && editing.line === target.line && editing.side === target.side;
    if (rowComments.length === 0 && !isEditing) return null;
    return (
      <div className={styles.rowAttachments}>
        {rowComments.map((c) => (
          <CommentCard key={c.id} comment={c} onRemove={() => onRemoveComment(c.id)} />
        ))}
        {isEditing && (
          <CommentEditor
            onSave={(text) => {
              onAddComment({ path: file.path, line: target.line, side: target.side, text });
              setEditing(null);
            }}
            onCancel={() => setEditing(null)}
          />
        )}
      </div>
    );
  };

  const handleRowClick = (row: DiffRow) => {
    const target = rowKey(row);
    if (target) setEditing(target);
  };

  if (!file.patch.trim()) {
    return <div className={styles.emptyPatch}>No textual diff (binary or empty file)</div>;
  }

  if (mode === "split") {
    return (
      <div className={styles.splitDiff}>
        {splitRows.map((sr, i) => {
          if (sr.hunk) {
            return (
              <div key={i} className={styles.hunkRowSplit}>{sr.hunk.content}</div>
            );
          }
          return (
            <div key={i} className={styles.splitPair}>
              {[sr.left, sr.right].map((cell, col) => (
                <div
                  key={col}
                  className={`${styles.splitCell} ${
                    cell?.type === "add" ? styles.addRow : cell?.type === "del" ? styles.delRow : cell ? "" : styles.blankCell
                  }`}
                  onClick={() => cell && handleRowClick(cell)}
                >
                  <span className={styles.lineNum}>
                    {cell ? (col === 0 ? cell.oldNum ?? "" : cell.newNum ?? "") : ""}
                  </span>
                  <span className={styles.lineContent}>{cell?.content ?? ""}</span>
                </div>
              ))}
              <div className={styles.splitAttachments}>
                {sr.left && sr.left !== sr.right && attachments(sr.left)}
                {sr.right && attachments(sr.right)}
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div className={styles.unifiedDiff}>
      {rows.map((row, i) => {
        if (row.type === "hunk") {
          return <div key={i} className={styles.hunkRow}>{row.content}</div>;
        }
        return (
          <div key={i}>
            <div
              className={`${styles.diffRow} ${
                row.type === "add" ? styles.addRow : row.type === "del" ? styles.delRow : ""
              }`}
              onClick={() => handleRowClick(row)}
              title="Click to comment"
            >
              <span className={styles.lineNum}>{row.oldNum ?? ""}</span>
              <span className={styles.lineNum}>{row.newNum ?? ""}</span>
              <span className={styles.lineSign}>
                {row.type === "add" ? "+" : row.type === "del" ? "−" : " "}
              </span>
              <span className={styles.lineContent}>{row.content}</span>
            </div>
            {attachments(row)}
          </div>
        );
      })}
    </div>
  );
}
