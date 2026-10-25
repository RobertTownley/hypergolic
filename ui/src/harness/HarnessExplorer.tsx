import { Text } from "@/shared/components/Text";
import { useCallback, useMemo, useState } from "react";
import { Tree, type TreeNode } from "@/shared/components/Tree";
import { DownloadIcon, FileIcon, FolderIcon, WrenchIcon } from "lucide-react";
import { IconButton } from "@/shared/components";
import { downloadHarnessConfig } from "@/api/files";
import { Panel, PanelHeader, PanelBody } from "@/shared/components/Panel";
import { Spinner } from "@/shared/components/Spinner";
import { useHarness } from "./useHarness";
import type { FileNode } from "@/types/api";
import styles from "@/files/FileExplorer/FileExplorer.module.css";

function fileNodeToTreeData(nodes: FileNode[]): TreeNode[] {
  return nodes.map((node) => ({
    key: node.path,
    title: <span className={styles.nodeTitle}><span style={{ color: "#e2e8f0" }}>{node.name}</span></span>,
    icon: node.is_dir
      ? <FolderIcon style={{ color: "#6366f1" }} />
      : <FileIcon style={{ color: "#64748b" }} />,
    isLeaf: !node.is_dir,
    children: node.is_dir && node.children ? fileNodeToTreeData(node.children) : undefined,
  }));
}

function getAncestorPaths(filePath: string): string[] {
  const parts = filePath.split("/");
  const ancestors: string[] = [];
  for (let i = 1; i < parts.length; i++) ancestors.push(parts.slice(0, i).join("/"));
  return ancestors;
}

export function HarnessExplorer() {
  const { loading, error, tree, selectedPath, selectPath, expandedPaths, setExpandedPaths } =
    useHarness();

  const expandedKeys = useMemo<string[]>(() => {
    if (!selectedPath) return expandedPaths;
    const ancestors = getAncestorPaths(selectedPath);
    const existing = new Set(expandedPaths);
    const merged: string[] = [...expandedPaths];
    for (const a of ancestors) {
      if (!existing.has(a)) merged.push(a);
    }
    return merged;
  }, [selectedPath, expandedPaths]);

  const treeData = useMemo(() => fileNodeToTreeData(tree), [tree]);

  const handleSelect = useCallback((key: string) => {
    if (key === selectedPath) return;
    selectPath(key);
  }, [selectedPath, selectPath]);

  const handleExpand = useCallback((keys: string[]) => {
    setExpandedPaths(keys);
  }, [setExpandedPaths]);

  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const handleExport = useCallback(async () => {
    setExporting(true);
    setExportError(null);
    try {
      await downloadHarnessConfig();
    } catch (err: unknown) {
      setExportError(err instanceof Error ? err.message : "Failed to export config");
    } finally {
      setExporting(false);
    }
  }, []);

  return (
    <Panel>
      <PanelHeader
        icon={<WrenchIcon />}
        actions={
          <IconButton
            size="medium"
            icon={<DownloadIcon />}
            onClick={handleExport}
            disabled={exporting}
            tooltip="Export config (.zip)"
            aria-label="Export config"
          />
        }
      >
        .hypergolic
      </PanelHeader>
      <PanelBody scrollable className={styles.treeContainer}>
        {exportError && (
          <Text type="danger" style={{ padding: "12px", display: "block" }}>{exportError}</Text>
        )}
        {error ? (
          <Text type="danger" style={{ padding: "12px", display: "block" }}>{error}</Text>
        ) : loading && tree.length === 0 ? (
          <Spinner centered />
        ) : (
          <Tree
            aria-label="Harness files"
            treeData={treeData}
            selectedKey={selectedPath}
            onSelect={handleSelect}
            expandedKeys={expandedKeys}
            onExpand={handleExpand}
          />
        )}
      </PanelBody>
    </Panel>
  );
}
