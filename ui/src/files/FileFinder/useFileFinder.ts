import { useCallback } from "react";
import { useAppDispatch, useAppSelector } from "@/store";
import { selectActiveProjectId, selectActiveSessionId } from "@/store/selectors";
import { selectFile } from "@/store/workspaceSlice";
import { loadFileContent } from "@/store/workspaceThunks";
import { setLeftTab } from "@/store/uiSlice";
import { setActiveSession } from "@/store/sessionsSlice";
import type { FinderResult } from "./types";
import {
  useFinderState,
  useFinderLifecycle,
  useSearch,
  useFilePreview,
  useSessionPreview,
  useFinderKeyboard,
  useResultScroll,
} from "./hooks";

export function useFileFinder() {
  const dispatch = useAppDispatch();
  const projectId = useAppSelector(selectActiveProjectId) ?? undefined;
  const activeSessionId = useAppSelector(selectActiveSessionId);

  const state = useFinderState();
  const {
    open, setOpen, query, setQuery, mode, setMode,
    respectGitignore, setRespectGitignore,
    includeHidden, setIncludeHidden,
    results, setResults, selectedIndex, setSelectedIndex,
    loading, setLoading,
    filePreview, setFilePreview, filePreviewLoading, setFilePreviewLoading,
    filePreviewError, setFilePreviewError,
    sessionMessages, setSessionMessages, sessionPreviewLoading, setSessionPreviewLoading,
    inputRef, resultsRef,
  } = state;

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    setResults([]);
    setSelectedIndex(0);
    setFilePreview(null);
    setFilePreviewError(null);
    setSessionMessages(null);
  }, [setOpen, setQuery, setResults, setSelectedIndex, setFilePreview, setFilePreviewError, setSessionMessages]);

  useFinderLifecycle(open, setOpen, close, inputRef);
  useSearch(open, query, mode, respectGitignore, includeHidden, projectId, setLoading, setResults, setSelectedIndex);

  const selectedResult = results[selectedIndex] as FinderResult | undefined;

  useFilePreview(open, selectedResult, activeSessionId, setFilePreviewLoading, setFilePreviewError, setFilePreview);
  useSessionPreview(open, selectedResult, setSessionPreviewLoading, setSessionMessages);

  const openResult = useCallback(
    (result: FinderResult) => {
      if (result.type === "file") {
        dispatch(setLeftTab("files"));
        dispatch(selectFile(result.match.path));
        if (activeSessionId) {
          dispatch(loadFileContent({ sessionId: activeSessionId, path: result.match.path }));
        }
      } else {
        dispatch(setActiveSession(result.match.session_id));
      }
      close();
    },
    [dispatch, close, activeSessionId],
  );

  const handleKeyDown = useFinderKeyboard(
    results, selectedIndex, setSelectedIndex, setMode, setRespectGitignore, setIncludeHidden, openResult, close,
  );

  useResultScroll(resultsRef, selectedIndex);

  const sessionPreviewLabel = selectedResult?.type === "session"
    ? selectedResult.match.first_message?.slice(0, 60) ?? "Session"
    : null;

  return {
    open, query, setQuery, mode, setMode,
    respectGitignore, setRespectGitignore,
    includeHidden, setIncludeHidden,
    results, selectedIndex, setSelectedIndex,
    loading,
    filePreview, filePreviewLoading, filePreviewError,
    sessionMessages, sessionPreviewLoading, sessionPreviewLabel,
    selectedResult, close, openResult, handleKeyDown,
    inputRef, resultsRef,
  };
}
