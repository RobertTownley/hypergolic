import { useCallback, useEffect, useMemo } from "react";
import { FileIcon, FolderIcon } from "lucide-react";
import { useAppDispatch, useAppSelector } from "@/store";
import {
  selectActiveSessionId,
  selectFileTree,
  selectFileTreeRoot,
  selectFileTreeLoading,
  selectSelectedFilePath,
  selectExpandedFilePaths,
} from "@/store/selectors";
import { selectFile, setExpandedFilePaths } from "@/store/workspaceSlice";
import { loadFileTree, loadFileContent } from "@/store/workspaceThunks";
import { useFileWatcher } from "@/hooks/useFileWatcher";
import type { FileNode } from "@/types/api";
import type { TreeNode } from "@/shared/components/Tree";
import styles from "./FileExplorer.module.css";

const STATUS_COLORS: Record<string, string> = {
  M: "#e2b714", MM: "#e2b714", AM: "#e2b714",
  A: "#4ade80", "??": "#4ade80",
  D: "#f87171", R: "#60a5fa", C: "#60a5fa",
  ignored: "#3a3a4e",
};

const STATUS_LABELS: Record<string, string> = {
  M: "M", MM: "M", AM: "M", A: "A", "??": "U", D: "D", R: "R", C: "C",
};

function fileNodeToTreeData(nodes: FileNode[]): TreeNode[] {
  return nodes.map((node) => {
    const color = node.git_status ? STATUS_COLORS[node.git_status] : undefined;
    const isIgnored = node.git_status === "ignored";
    const statusLabel = node.git_status ? STATUS_LABELS[node.git_status] : undefined;
    const titleElement = (
      <span className={styles.nodeTitle} style={{ opacity: isIgnored ? 0.4 : 1 }}>
        <span style={{ color: color ?? "#e2e8f0" }}>{node.name}</span>
        {statusLabel && <span className={styles.statusBadge} style={{ color }}>{statusLabel}</span>}
      </span>
    );
    const base: TreeNode = {
      key: node.path,
      title: titleElement,
      icon: node.is_dir
        ? <FolderIcon style={{ color: isIgnored ? "#3a3a4e" : "#6366f1" }} />
        : <FileIcon style={{ color: isIgnored ? "#3a3a4e" : "#64748b" }} />,
      isLeaf: !node.is_dir,
    };
    if (node.is_dir && node.children) base.children = fileNodeToTreeData(node.children);
    return base;
  });
}

function findNode(nodes: FileNode[], path: string): FileNode | null {
  for (const node of nodes) {
    if (node.path === path) return node;
    if (node.children) {
      const found = findNode(node.children, path);
      if (found) return found;
    }
  }
  return null;
}

function isDir(tree: FileNode[], path: string): boolean {
  return findNode(tree, path)?.is_dir ?? false;
}

function getAncestorPaths(filePath: string): string[] {
  const parts = filePath.split("/");
  const ancestors: string[] = [];
  for (let i = 1; i < parts.length; i++) ancestors.push(parts.slice(0, i).join("/"));
  return ancestors;
}

export function useFileExplorer() {
  const dispatch = useAppDispatch();
  const tree = useAppSelector(selectFileTree);
  const root = useAppSelector(selectFileTreeRoot);
  const loading = useAppSelector(selectFileTreeLoading);
  const selectedFilePath = useAppSelector(selectSelectedFilePath);
  const expandedFilePaths = useAppSelector(selectExpandedFilePaths);
  const activeSessionId = useAppSelector(selectActiveSessionId);

  useEffect(() => {
    if (!activeSessionId) return;
    dispatch(loadFileTree({ sessionId: activeSessionId }));
  }, [dispatch, activeSessionId]);

  // Derive expanded keys by merging stored paths with ancestors of selected file.
  const expandedKeys: string[] = useMemo(() => {
    if (!selectedFilePath) return expandedFilePaths;
    const ancestors = getAncestorPaths(selectedFilePath);
    const existing = new Set(expandedFilePaths);
    const merged = [...expandedFilePaths];
    for (const a of ancestors) {
      if (!existing.has(a)) merged.push(a);
    }
    return merged;
  }, [selectedFilePath, expandedFilePaths]);

  const refreshTree = useMemo(
    () => () => { if (activeSessionId) dispatch(loadFileTree({ sessionId: activeSessionId })); },
    [dispatch, activeSessionId],
  );

  useFileWatcher(refreshTree);

  const treeData = useMemo(() => fileNodeToTreeData(tree), [tree]);
  const rootName = root ? root.split("/").pop() : "Project";

  const handleSelect = (key: string) => {
    if (key === selectedFilePath) return;
    dispatch(selectFile(key));
    if (!isDir(tree, key) && activeSessionId) {
      dispatch(loadFileContent({ sessionId: activeSessionId, path: key }));
    }
  };

  const handleExpand = useCallback((keys: string[]) => {
    dispatch(setExpandedFilePaths(keys));
  }, [dispatch]);

  return { loading, tree, treeData, rootName, selectedFilePath, expandedKeys, handleSelect, handleExpand, refresh: refreshTree };
}
