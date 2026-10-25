import { FileDiffIcon, XIcon } from "lucide-react";
import { SelectionBar } from "@/layout/SelectionBar";
import type { CodeSelection } from "@/types/api";
import { EmptyState } from "@/shared/components/EmptyState";
import { IconButton, Spinner } from "@/shared/components";
import { useDiffViewer } from "./useDiffViewer";
import styles from "./DiffViewer.module.css";

interface DiffViewerProps {
  onAttachSelection?: (selection: CodeSelection) => void;
}

export function DiffViewer({ onAttachSelection }: DiffViewerProps) {
  const {
    selectedDiff,
    diffLoading,
    diffLines,
    lineSelection,
    selecting,
    bounds,
    selectionLabel,
    handleLineMouseDown,
    handleLineMouseEnter,
    clearSelection,
    handleOpenFile,
    handleCloseDiff,
    handleAttach,
  } = useDiffViewer(onAttachSelection);

  if (!selectedDiff && !diffLoading) return null;

  if (diffLoading) {
    return (
      <div className={styles.container}>
        <div className={styles.loadingState}>
          <Spinner />
        </div>
      </div>
    );
  }

  if (!selectedDiff?.diff) {
    return (
      <div className={styles.container}>
        <div className={styles.header}>
          <FileDiffIcon style={{ color: "#6366f1" }} />
          <button className={styles.filePathBtn} onClick={handleOpenFile} title="Open in file explorer">
            {selectedDiff?.path}
          </button>
          <IconButton size="medium" icon={<XIcon />} onClick={handleCloseDiff} style={{ marginLeft: "auto" }} />
        </div>
        <EmptyState text="No diff available" />
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <FileDiffIcon style={{ color: "#6366f1" }} />
        <button className={styles.filePathBtn} onClick={handleOpenFile} title="Open in file explorer">
          {selectedDiff.path}
        </button>
        <IconButton size="medium" icon={<XIcon />} onClick={handleCloseDiff} style={{ marginLeft: "auto" }} />
      </div>
      {lineSelection && (
        <SelectionBar
          label={selectionLabel}
          onAttach={onAttachSelection ? handleAttach : undefined}
          onClear={clearSelection}
        />
      )}
      <div className={styles.diffContent}>
        {diffLines.map((line, i) => {
          const isSelected = bounds !== null && i >= bounds.selStart && i <= bounds.selEnd;
          return (
            <div
              key={i}
              className={`${styles.diffLine} ${styles[line.type]} ${isSelected ? styles.selectedLine : ""}`}
              style={{ cursor: selecting ? "grabbing" : "pointer" }}
              onMouseDown={(e) => {
                e.preventDefault();
                handleLineMouseDown(i, e.shiftKey);
              }}
              onMouseEnter={() => handleLineMouseEnter(i)}
            >
              <span className={styles.lineNumber}>{line.oldNum ?? ""}</span>
              <span className={styles.lineNumber}>{line.newNum ?? ""}</span>
              <span className={styles.lineContent}>{line.content}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
