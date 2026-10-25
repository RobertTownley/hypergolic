import { MinusIcon } from "lucide-react";
import type { ChangedFile } from "@/types/api";
import {
  DiffTotals,
  FileItemRow,
  TreeSection,
  type FileTreeNode,
} from "@/git/FileTree";
import { IconButton } from "@/shared/components";
import styles from "./VersionControl.module.css";

export function StagedSection({
  stagedFiles,
  stagedTree,
  expandedDirs,
  toggleDir,
  onSelectFile,
  onUnstageFile,
  onUnstageAll,
}: {
  stagedFiles: ChangedFile[];
  stagedTree: FileTreeNode;
  expandedDirs: Set<string>;
  toggleDir: (path: string) => void;
  onSelectFile: (path: string) => void;
  onUnstageFile: (path: string) => void;
  onUnstageAll: () => void;
}) {
  return (
    <>
      <div className={styles.sectionHeader}>
        <span>Staged ({stagedFiles.length})<DiffTotals files={stagedFiles} /></span>
        <span className={styles.sectionActions}>
          <IconButton
            size="small"
            icon={<MinusIcon />}
            tooltip="Unstage all"
            onClick={onUnstageAll}
          />
        </span>
      </div>
      <TreeSection
        tree={stagedTree}
        depth={0}
        expandedDirs={expandedDirs}
        toggleDir={toggleDir}
        renderFile={(node, depth) => {
          if (!node.file) return null;
          const f = node.file;
          return (
            <FileItemRow
              key={`staged-${f.path}`}
              file={f}
              depth={depth}
              onSelect={() => onSelectFile(f.path)}
              actions={
                <IconButton
                  size="small"
                  icon={<MinusIcon />}
                  tooltip="Unstage"
                  onClick={(e) => {
                    e.stopPropagation();
                    onUnstageFile(f.path);
                  }}
                />
              }
            />
          );
        }}
      />
    </>
  );
}
