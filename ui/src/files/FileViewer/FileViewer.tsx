import { Text } from "@/shared/components/Text";
import { FolderOpenIcon } from "lucide-react";
import { SelectionBar } from "@/layout/SelectionBar";
import type { CodeSelection } from "@/types/api";
import { EmptyState } from "@/shared/components/EmptyState";
import { Spinner } from "@/shared/components/Spinner";
import { FileHeader } from "./FileHeader";
import { MarkdownView } from "./MarkdownView";
import { CodeView } from "./CodeView";
import { DirectoryView } from "./DirectoryView";
import { useFileViewer } from "./useFileViewer";
import styles from "./FileViewer.module.css";

interface FileViewerProps {
  onAttachSelection?: (selection: CodeSelection) => void;
}

export function FileViewer({ onAttachSelection }: FileViewerProps) {
  const {
    selectedFilePath,
    selectedNode,
    fileContent,
    fileContentTruncated,
    fileContentLoading,
    fileContentError,
    lineSelection,
    selecting,
    bounds,
    handleLineMouseDown,
    handleLineMouseEnter,
    clearSelection,
    handleAttach,
  } = useFileViewer(onAttachSelection);

  if (!selectedFilePath) {
    return (
      <EmptyState
        icon={<FolderOpenIcon />}
        text="Select a file to view"
        className={styles.emptyState}
      >
        <span className={styles.emptyHint}>Choose a file from the explorer</span>
      </EmptyState>
    );
  }

  if (selectedNode?.is_dir) {
    return <DirectoryView path={selectedFilePath} entries={selectedNode.children} />;
  }

  if (fileContentLoading) {
    return (
      <div className={styles.loadingState}>
        <Spinner />
      </div>
    );
  }

  if (fileContentError) {
    return (
      <div className={styles.errorState}>
        <Text type="danger">{fileContentError}</Text>
      </div>
    );
  }

  if (!fileContent) return null;

  const isMarkdown = fileContent.language === "markdown";

  return (
    <div className={styles.container}>
      <FileHeader path={fileContent.path} />
      {lineSelection && bounds && (
        <SelectionBar
          label={
            bounds.selStart === bounds.selEnd
              ? `Line ${bounds.selStart} selected`
              : `Lines ${bounds.selStart}-${bounds.selEnd} selected`
          }
          onAttach={onAttachSelection ? handleAttach : undefined}
          onClear={clearSelection}
        />
      )}
      {fileContentTruncated && (
        <div className={styles.truncatedBanner}>
          File truncated — showing the first portion only.
        </div>
      )}
      <div className={styles.contentArea}>
        {isMarkdown ? (
          <MarkdownView content={fileContent.content} />
        ) : (
          <CodeView
            content={fileContent.content}
            language={fileContent.language}
            selection={lineSelection}
            onLineMouseDown={handleLineMouseDown}
            onLineMouseEnter={handleLineMouseEnter}
            selecting={selecting}
          />
        )}
      </div>
    </div>
  );
}
