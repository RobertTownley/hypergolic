import { ChevronDownIcon, ChevronRightIcon, FolderIcon, PlusIcon } from "lucide-react";
import { IconButton } from "@/shared/components";
import type { TreeFile } from "./treeModel";
import { STATUS_COLORS } from "./constants";
import styles from "./FileTree.module.css";

export function FileItemRow({
  file,
  onSelect,
  actions,
  depth,
  selected = false,
  leading,
}: {
  file: TreeFile;
  onSelect: () => void;
  actions: React.ReactNode;
  depth: number;
  selected?: boolean;
  leading?: React.ReactNode;
}) {
  const color = STATUS_COLORS[file.status] ?? "#94a3b8";
  return (
    <div
      className={`${styles.fileItem} ${selected ? styles.fileItemActive : ""}`}
      onClick={onSelect}
      style={{ paddingLeft: 14 + depth * 12 }}
    >
      {leading}
      <span className={styles.statusBadge} style={{ color }}>
        {file.status}
      </span>
      <span className={styles.fileName} title={file.path}>{file.path.split("/").pop()}</span>
      <span className={styles.fileMeta}>
        {file.additions > 0 && (
          <span className={styles.additions}>+{file.additions}</span>
        )}
        {file.deletions > 0 && (
          <span className={styles.deletions}>-{file.deletions}</span>
        )}
      </span>
      {actions && <span className={styles.fileActions}>{actions}</span>}
    </div>
  );
}

export function UntrackedRow({
  path,
  onSelect,
  onStage,
  depth,
}: {
  path: string;
  onSelect: () => void;
  onStage: () => void;
  depth: number;
}) {
  return (
    <div
      className={styles.fileItem}
      onClick={onSelect}
      style={{ paddingLeft: 14 + depth * 12 }}
    >
      <span className={styles.statusBadge} style={{ color: "#4ade80" }}>
        U
      </span>
      <span className={styles.fileName} title={path}>{path.split("/").pop()}</span>
      <span className={styles.fileMeta} />
      <span className={styles.fileActions}>
        <IconButton
          size="small"
          icon={<PlusIcon />}
          tooltip="Stage"
          onClick={(e) => {
            e.stopPropagation();
            onStage();
          }}
        />
      </span>
    </div>
  );
}

export function DirRow({
  name,
  expanded,
  onToggle,
  depth,
}: {
  name: string;
  expanded: boolean;
  onToggle: () => void;
  depth: number;
}) {
  return (
    <div
      className={styles.dirItem}
      onClick={onToggle}
      style={{ paddingLeft: 14 + depth * 12 }}
    >
      <span className={styles.dirChevron}>
        {expanded ? <ChevronDownIcon /> : <ChevronRightIcon />}
      </span>
      <FolderIcon className={styles.dirIcon} />
      <span className={styles.dirName}>{name}</span>
    </div>
  );
}

export function DiffTotals({ files }: { files: TreeFile[] }) {
  const additions = files.reduce((sum, f) => sum + f.additions, 0);
  const deletions = files.reduce((sum, f) => sum + f.deletions, 0);
  if (additions === 0 && deletions === 0) return null;
  return (
    <span className={styles.diffTotals}>
      {additions > 0 && <span className={styles.additions}>+{additions}</span>}
      {deletions > 0 && <span className={styles.deletions}>-{deletions}</span>}
    </span>
  );
}
