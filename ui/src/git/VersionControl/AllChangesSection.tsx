import type { ChangedFile } from "@/types/api";
import {
  DiffTotals,
  FileItemRow,
  TreeSection,
  type FileTreeNode,
} from "@/git/FileTree";
import styles from "./VersionControl.module.css";

// Read-only view of every file that differs from the base branch
// (committed branch work + uncommitted edits). Staging/discarding don't
// apply here — the diff spans commits — so rows are click-to-diff only.
export function AllChangesSection({
  allChanges,
  allChangesTree,
  baseBranch,
  expandedDirs,
  toggleDir,
  onSelectFile,
}: {
  allChanges: ChangedFile[];
  allChangesTree: FileTreeNode;
  baseBranch: string | null;
  expandedDirs: Set<string>;
  toggleDir: (path: string) => void;
  onSelectFile: (path: string) => void;
}) {
  const label = baseBranch ? `Changes vs ${baseBranch}` : "Changes";
  return (
    <>
      <div className={styles.sectionHeader}>
        <span>{label} ({allChanges.length})<DiffTotals files={allChanges} /></span>
      </div>
      <TreeSection
        tree={allChangesTree}
        depth={0}
        expandedDirs={expandedDirs}
        toggleDir={toggleDir}
        renderFile={(node, depth) => {
          if (!node.file) return null;
          const f = node.file;
          return (
            <FileItemRow
              key={`all-${f.path}`}
              file={f}
              depth={depth}
              onSelect={() => onSelectFile(f.path)}
              actions={null}
            />
          );
        }}
      />
    </>
  );
}
