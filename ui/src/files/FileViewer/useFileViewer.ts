import { useCallback } from "react";
import { useAppSelector } from "@/store";
import {
  selectSelectedFilePath,
  selectFileContent,
  selectFileContentLoading,
  selectFileContentError,
  selectFileTree,
  selectFileSource,
  selectSandboxSelectedPath,
  selectSandboxContent,
  selectSandboxContentLoading,
  selectSandboxContentError,
  selectSandboxDirCache,
} from "@/store/selectors";
import { useLineSelection, selectionBounds } from "@/hooks/useLineSelection";
import type { CodeSelection, FileNode } from "@/types/api";

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

interface ViewerContent {
  path: string;
  content: string;
  language: string;
  truncated?: boolean;
}

export function useFileViewer(onAttachSelection?: (selection: CodeSelection) => void) {
  const fileSource = useAppSelector(selectFileSource);

  const hostPath = useAppSelector(selectSelectedFilePath);
  const hostContent = useAppSelector(selectFileContent);
  const hostLoading = useAppSelector(selectFileContentLoading);
  const hostError = useAppSelector(selectFileContentError);
  const tree = useAppSelector(selectFileTree);

  const sandboxPath = useAppSelector(selectSandboxSelectedPath);
  const sandboxContent = useAppSelector(selectSandboxContent);
  const sandboxLoading = useAppSelector(selectSandboxContentLoading);
  const sandboxError = useAppSelector(selectSandboxContentError);
  const sandboxDirCache = useAppSelector(selectSandboxDirCache);

  const isSandbox = fileSource === "sandbox";

  const selectedFilePath = isSandbox ? sandboxPath : hostPath;
  const fileContent: ViewerContent | null = isSandbox ? sandboxContent : hostContent;
  const fileContentLoading = isSandbox ? sandboxLoading : hostLoading;
  const fileContentError = isSandbox ? sandboxError : hostError;

  // For the host tree, directory contents come from the nested node. For the
  // sandbox tree, a selected directory is identified by a hit in the lazy dir
  // cache; its children come straight from that cache entry.
  const selectedNode: FileNode | null = isSandbox
    ? selectedFilePath && sandboxDirCache[selectedFilePath]
      ? {
          name: selectedFilePath.split("/").pop() ?? selectedFilePath,
          path: selectedFilePath,
          is_dir: true,
          git_status: null,
          children: sandboxDirCache[selectedFilePath].map((n) => ({
            name: n.name,
            path: n.path,
            is_dir: n.is_dir,
            git_status: null,
            children: null,
          })),
        }
      : null
    : selectedFilePath
      ? findNode(tree, selectedFilePath)
      : null;

  const {
    lineSelection,
    selecting,
    handleLineMouseDown,
    handleLineMouseEnter,
    clearSelection,
    setLineSelection,
  } = useLineSelection();

  const bounds = lineSelection ? selectionBounds(lineSelection) : null;

  const handleAttach = useCallback(() => {
    if (!bounds || !fileContent || !onAttachSelection) return;

    const lines = fileContent.content.split("\n");
    const selectedLines = lines.slice(bounds.selStart - 1, bounds.selEnd).join("\n");

    onAttachSelection({
      filePath: fileContent.path,
      startLine: bounds.selStart,
      endLine: bounds.selEnd,
      content: selectedLines,
      language: fileContent.language,
    });

    setLineSelection(null);
  }, [bounds, fileContent, onAttachSelection, setLineSelection]);

  return {
    selectedFilePath,
    selectedNode,
    fileContent,
    fileContentTruncated: isSandbox ? sandboxContent?.truncated ?? false : false,
    fileContentLoading,
    fileContentError,
    lineSelection,
    selecting,
    bounds,
    handleLineMouseDown,
    handleLineMouseEnter,
    clearSelection,
    handleAttach,
  };
}
