import { PlusIcon, Undo2Icon } from "lucide-react";
import type { ChangedFile } from "@/types/api";
import {
  DiffTotals,
  FileItemRow,
  UntrackedRow,
  TreeSection,
  getAllPaths,
  type FileTreeNode,
} from "@/git/FileTree";
import { IconButton } from "@/shared/components";
import styles from "./VersionControl.module.css";

export function ChangesSection({
  unstagedFiles,
  untrackedFiles,
  unstagedTree,
  expandedDirs,
  toggleDir,
  onSelectFile,
  onStageFile,
  onDiscardFile,
  onStageAll,
  onDiscardAll,
}: {
  unstagedFiles: ChangedFile[];
  untrackedFiles: string[];
  unstagedTree: FileTreeNode;
  expandedDirs: Set<string>;
  toggleDir: (path: string) => void;
  onSelectFile: (path: string) => void;
  onStageFile: (path: string) => void;
  onDiscardFile: (path: string) => void;
  onStageAll: (paths: string[]) => void;
  onDiscardAll: () => void;
}) {
  const hasUnstaged = unstagedFiles.length > 0;
  const totalCount = unstagedFiles.length + untrackedFiles.length;

  return (
    <>
      <div className={styles.sectionHeader}>
        <span>Changes ({totalCount})<DiffTotals files={unstagedFiles} /></span>
        <span className={styles.sectionActions}>
          <IconButton
            size="small"
            icon={<PlusIcon />}
            tooltip="Stage all"
            onClick={() => onStageAll(getAllPaths(unstagedTree))}
          />
          {hasUnstaged && (
            <IconButton
              size="small"
              icon={<Undo2Icon />}
              tooltip="Discard all"
              onClick={onDiscardAll}
            />
          )}
        </span>
      </div>
      <TreeSection
        tree={unstagedTree}
        depth={0}
        expandedDirs={expandedDirs}
        toggleDir={toggleDir}
        renderFile={(node, depth) => {
          if (node.file) {
            const f = node.file;
            return (
              <FileItemRow
                key={`unstaged-${f.path}`}
                file={f}
                depth={depth}
                onSelect={() => onSelectFile(f.path)}
                actions={
                  <>
                    <IconButton
                      size="small"
                      icon={<PlusIcon />}
                      tooltip="Stage"
                      onClick={(e) => {
                        e.stopPropagation();
                        onStageFile(f.path);
                      }}
                    />
                    <IconButton
                      size="small"
                      icon={<Undo2Icon />}
                      tooltip="Discard"
                      onClick={(e) => {
                        e.stopPropagation();
                        onDiscardFile(f.path);
                      }}
                    />
                  </>
                }
              />
            );
          }
          if (node.untrackedPath) {
            return (
              <UntrackedRow
                key={`untracked-${node.untrackedPath}`}
                path={node.untrackedPath}
                depth={depth}
                onSelect={() => onSelectFile(node.untrackedPath!)}
                onStage={() => onStageFile(node.untrackedPath!)}
              />
            );
          }
          return null;
        }}
      />
    </>
  );
}
