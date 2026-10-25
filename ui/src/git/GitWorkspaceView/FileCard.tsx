import { useMemo, useState } from "react";
import { ChevronDownIcon, ChevronRightIcon } from "lucide-react";
import type { GitReviewFile } from "@/types/api";
import { parseDiff } from "@/shared/diff";
import { DiffRows } from "./DiffRows";
import styles from "./GitWorkspaceView.module.css";

const STATUS_LABEL: Record<string, string> = {
  A: "added",
  D: "deleted",
  R: "renamed",
  "?": "new",
};

export function FileCard({ file, defaultCollapsed = false }: { file: GitReviewFile; defaultCollapsed?: boolean }) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  // Skip parsing entirely while collapsed; big changesets render headers only.
  const rows = useMemo(() => (collapsed ? [] : parseDiff(file.patch)), [file.patch, collapsed]);
  const label = STATUS_LABEL[file.status];

  return (
    <div className={styles.fileCard}>
      <button
        type="button"
        className={styles.fileHeader}
        onClick={() => setCollapsed((c) => !c)}
      >
        <span className={styles.chevron}>
          {collapsed ? <ChevronRightIcon /> : <ChevronDownIcon />}
        </span>
        <span className={styles.filePath} title={file.path}>
          {file.old_path ? `${file.old_path} → ${file.path}` : file.path}
        </span>
        {label && <span className={styles.statusTag}>{label}</span>}
        <span className={styles.fileStats}>
          <span className={styles.add}>+{file.additions}</span>{" "}
          <span className={styles.del}>−{file.deletions}</span>
        </span>
      </button>
      {!collapsed &&
        (rows.length === 0 ? (
          <div className={styles.noPreview}>No preview available</div>
        ) : (
          <DiffRows rows={rows} />
        ))}
    </div>
  );
}
