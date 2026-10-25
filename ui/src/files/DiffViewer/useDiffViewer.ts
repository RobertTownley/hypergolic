import { useCallback } from "react";
import { useAppDispatch, useAppSelector } from "@/store";
import { selectActiveSessionId, selectSelectedDiff, selectDiffLoading } from "@/store/selectors";
import { clearDiff, selectFile } from "@/store/workspaceSlice";
import { loadFileContent } from "@/store/workspaceThunks";
import { setLeftTab } from "@/store/uiSlice";
import { useLineSelection, selectionBounds } from "@/hooks/useLineSelection";
import type { CodeSelection } from "@/types/api";
import { parseDiff, type DiffRow } from "@/shared/diff";

function diffLinePrefix(type: DiffRow["type"]): string {
  if (type === "add") return "+";
  if (type === "del") return "-";
  return " ";
}

export function useDiffViewer(onAttachSelection?: (selection: CodeSelection) => void) {
  const dispatch = useAppDispatch();
  const selectedDiff = useAppSelector(selectSelectedDiff);
  const diffLoading = useAppSelector(selectDiffLoading);
  const activeSessionId = useAppSelector(selectActiveSessionId);
  const {
    lineSelection,
    selecting,
    handleLineMouseDown,
    handleLineMouseEnter,
    clearSelection,
    setLineSelection,
  } = useLineSelection();

  const bounds = lineSelection ? selectionBounds(lineSelection) : null;

  const handleOpenFile = useCallback(() => {
    if (!selectedDiff?.path || !activeSessionId) return;
    dispatch(clearDiff());
    dispatch(setLeftTab("files"));
    dispatch(selectFile(selectedDiff.path));
    dispatch(loadFileContent({ sessionId: activeSessionId, path: selectedDiff.path }));
  }, [dispatch, selectedDiff, activeSessionId]);

  const handleCloseDiff = useCallback(() => {
    dispatch(clearDiff());
  }, [dispatch]);

  const handleAttach = useCallback(() => {
    if (!bounds || !selectedDiff?.diff || !onAttachSelection) return;
    const diffLines = parseDiff(selectedDiff.diff);
    const selectedLines = diffLines
      .slice(bounds.selStart, bounds.selEnd + 1)
      .map((l) => `${diffLinePrefix(l.type)}${l.content}`);

    onAttachSelection({
      filePath: selectedDiff.path,
      startLine: bounds.selStart + 1,
      endLine: bounds.selEnd + 1,
      content: selectedLines.join("\n"),
      language: "diff",
    });
    setLineSelection(null);
  }, [bounds, selectedDiff, onAttachSelection, setLineSelection]);

  const diffLines = selectedDiff?.diff ? parseDiff(selectedDiff.diff) : [];
  const lineCount = bounds ? bounds.selEnd - bounds.selStart + 1 : 0;
  const selectionLabel = lineCount === 1 ? "1 line selected" : `${lineCount} lines selected`;

  return {
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
  };
}
