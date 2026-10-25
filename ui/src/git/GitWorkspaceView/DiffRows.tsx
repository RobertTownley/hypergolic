import { useState } from "react";
import type { DiffRow } from "@/shared/diff";
import styles from "./GitWorkspaceView.module.css";

// Cap rendered rows so one huge file can't blow up the scroll layer
// (Chrome stops painting text in very tall composited layers).
const ROW_CAP = 300;

function Row({ row }: { row: DiffRow }) {
  if (row.type === "hunk") {
    return <div className={styles.hunkRow}>{row.content}</div>;
  }
  const rowClass =
    row.type === "add" ? styles.addRow : row.type === "del" ? styles.delRow : "";
  return (
    <div className={`${styles.diffRow} ${rowClass}`}>
      <span className={styles.lineNum}>{row.oldNum ?? ""}</span>
      <span className={styles.lineNum}>{row.newNum ?? ""}</span>
      <span className={styles.lineSign}>
        {row.type === "add" ? "+" : row.type === "del" ? "−" : ""}
      </span>
      <span className={styles.lineContent}>{row.content}</span>
    </div>
  );
}

export function DiffRows({ rows }: { rows: DiffRow[] }) {
  const [showAll, setShowAll] = useState(false);
  const visible = showAll ? rows : rows.slice(0, ROW_CAP);
  const hidden = rows.length - visible.length;

  return (
    <div className={styles.diffBody}>
      {visible.map((row, i) => (
        <Row key={i} row={row} />
      ))}
      {hidden > 0 && (
        <button type="button" className={styles.showMoreBtn} onClick={() => setShowAll(true)}>
          Show remaining {hidden} lines
        </button>
      )}
    </div>
  );
}
