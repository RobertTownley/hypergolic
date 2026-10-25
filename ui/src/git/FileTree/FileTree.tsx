import { type FileTreeNode, sortedChildren } from "./treeModel";
import { DirRow } from "./FileRows";

export { buildTree, getAllPaths, orderedFilePaths } from "./treeModel";
export type { FileTreeNode } from "./treeModel";
export { useExpandedDirs } from "./useExpandedDirs";
export { DiffTotals, FileItemRow, UntrackedRow } from "./FileRows";

export function TreeSection({
  tree,
  depth,
  expandedDirs,
  toggleDir,
  renderFile,
}: {
  tree: FileTreeNode;
  depth: number;
  expandedDirs: Set<string>;
  toggleDir: (path: string) => void;
  renderFile: (node: FileTreeNode, depth: number) => React.ReactNode;
}) {
  const children = sortedChildren(tree);
  return (
    <>
      {children.map((child) => {
        const isDir = child.children.size > 0 && !child.file && !child.untrackedPath;
        if (isDir) {
          const expanded = expandedDirs.has(child.path);
          return (
            <div key={`dir-${child.path}`}>
              <DirRow
                name={child.name}
                expanded={expanded}
                onToggle={() => toggleDir(child.path)}
                depth={depth}
              />
              {expanded && (
                <TreeSection
                  tree={child}
                  depth={depth + 1}
                  expandedDirs={expandedDirs}
                  toggleDir={toggleDir}
                  renderFile={renderFile}
                />
              )}
            </div>
          );
        }
        return <div key={`file-${child.path}`}>{renderFile(child, depth)}</div>;
      })}
    </>
  );
}
