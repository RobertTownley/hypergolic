// Thin selectors+dispatch wrapper over the Redux harnessSlice, which holds
// harness state so it survives left-tab switches.
import { useCallback, useEffect } from "react";
import { useAppDispatch, useAppSelector } from "@/store";
import {
  loadHarnessTree,
  loadHarnessFileContent,
  selectHarnessFile,
  setHarnessExpandedPaths,
  invalidateHarnessContent,
  selectHarnessTree,
  selectHarnessTreeLoaded,
  selectHarnessLoading,
  selectHarnessError,
  selectHarnessSelectedPath,
  selectHarnessFileContent,
  selectHarnessFileLoading,
  selectHarnessFileError,
  selectHarnessExpandedPaths,
} from "@/store/harnessSlice";

export function useHarness() {
  const dispatch = useAppDispatch();
  const loading = useAppSelector(selectHarnessLoading);
  const error = useAppSelector(selectHarnessError);
  const tree = useAppSelector(selectHarnessTree);
  const treeLoaded = useAppSelector(selectHarnessTreeLoaded);
  const selectedPath = useAppSelector(selectHarnessSelectedPath);
  const fileContent = useAppSelector(selectHarnessFileContent);
  const fileLoading = useAppSelector(selectHarnessFileLoading);
  const fileError = useAppSelector(selectHarnessFileError);
  const expandedPaths = useAppSelector(selectHarnessExpandedPaths);

  // First load only: treeLoaded persists in the store, so remounting the
  // harness tab does not refetch. Multiple consumers (explorer + viewer)
  // dispatch concurrently; the dedupe middleware collapses them.
  useEffect(() => {
    if (!treeLoaded) void dispatch(loadHarnessTree());
  }, [treeLoaded, dispatch]);

  const selectPath = useCallback(
    (path: string) => {
      dispatch(selectHarnessFile(path));
      // The thunk's condition skips the fetch when the path is cached.
      void dispatch(loadHarnessFileContent({ path }));
    },
    [dispatch],
  );

  const refresh = useCallback(() => {
    dispatch(invalidateHarnessContent());
    void dispatch(loadHarnessTree());
    if (selectedPath) void dispatch(loadHarnessFileContent({ path: selectedPath }));
  }, [dispatch, selectedPath]);

  const setExpandedPaths = useCallback(
    (paths: string[]) => {
      dispatch(setHarnessExpandedPaths(paths));
    },
    [dispatch],
  );

  return {
    loading,
    error,
    tree,
    selectedPath,
    fileContent,
    fileLoading,
    fileError,
    expandedPaths,
    selectPath,
    setExpandedPaths,
    refresh,
  };
}
