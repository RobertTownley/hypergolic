import { useEffect, useMemo, useCallback } from "react";
import type { TreeNode } from "@/shared/components/Tree";
import { useAppDispatch, useAppSelector } from "@/store";
import { setSandboxContainer, setSandboxRoot, selectSandboxFile, setSandboxExpandedPaths, refreshSandbox } from "@/store/workspaceSlice";
import { loadSandboxContainers, loadSandboxDir, loadSandboxContent } from "@/store/workspaceThunks";
import {
  selectActiveSessionId,
  selectSandboxContainers,
  selectSandboxContainersLoaded,
  selectSandboxContainer,
  selectSandboxRoot,
  selectSandboxDirCache,
  selectSandboxExpandedPaths,
  selectSandboxSelectedPath,
  selectSandboxLoading,
  selectSandboxError,
  selectSandboxStarting,
} from "@/store/selectors";

// The sandbox comes up in the background from session creation; poll until the
// container answers rather than making the user hit refresh.
const STARTING_RETRY_MS = 2000;

function buildTree(
  parentPath: string,
  dirCache: Record<string, import("@/types/api").SandboxNode[]>,
): TreeNode[] {
  const nodes = dirCache[parentPath];
  if (!nodes) return [];
  return nodes.map((n) => ({
    key: n.path,
    title: n.name,
    isLeaf: !n.is_dir,
    children: n.is_dir ? buildTree(n.path, dirCache) : undefined,
  }));
}

export function useSandboxExplorer() {
  const dispatch = useAppDispatch();
  const sessionId = useAppSelector(selectActiveSessionId);

  const containers = useAppSelector(selectSandboxContainers);
  const containersLoaded = useAppSelector(selectSandboxContainersLoaded);
  const container = useAppSelector(selectSandboxContainer);
  const root = useAppSelector(selectSandboxRoot);
  const dirCache = useAppSelector(selectSandboxDirCache);
  const expandedKeys = useAppSelector(selectSandboxExpandedPaths);
  const selectedPath = useAppSelector(selectSandboxSelectedPath);
  const loading = useAppSelector(selectSandboxLoading);
  const error = useAppSelector(selectSandboxError);
  const starting = useAppSelector(selectSandboxStarting);

  const activeContainer = containers.find((c) => c.id === container) ?? null;
  const roots = activeContainer?.roots ?? [];
  const rootPath = roots.find((r) => r.id === root)?.path ?? null;

  useEffect(() => {
    if (sessionId && !containersLoaded) {
      dispatch(loadSandboxContainers({ sessionId }));
    }
  }, [dispatch, sessionId, containersLoaded]);

  // Load the top-level listing whenever the container/root is set and the
  // root level hasn't been cached yet.
  useEffect(() => {
    if (sessionId && container && root && rootPath && dirCache[rootPath] === undefined) {
      dispatch(loadSandboxDir({ sessionId, container, root: rootPath, rootId: root, path: null }));
    }
  }, [dispatch, sessionId, container, root, rootPath, dirCache]);

  // Re-armed by `loading` flipping around each attempt, so one timeout keeps
  // the poll going for as long as the container is still starting.
  useEffect(() => {
    if (!starting || loading || !sessionId || !container || !root || !rootPath) return;
    const timer = setTimeout(() => {
      dispatch(loadSandboxDir({ sessionId, container, root: rootPath, rootId: root, path: null }));
    }, STARTING_RETRY_MS);
    return () => clearTimeout(timer);
  }, [dispatch, starting, loading, sessionId, container, root, rootPath]);

  const treeData = useMemo(
    () => (rootPath ? buildTree(rootPath, dirCache) : []),
    [rootPath, dirCache],
  );

  const handleSelectContainer = useCallback(
    (value: string) => dispatch(setSandboxContainer(value)),
    [dispatch],
  );

  const handleSelectRoot = useCallback(
    (value: string) => dispatch(setSandboxRoot(value)),
    [dispatch],
  );

  const handleExpand = useCallback(
    (keys: string[]) => {
      dispatch(setSandboxExpandedPaths(keys));
    },
    [dispatch],
  );

  const handleLoadData = useCallback(
    async (node: TreeNode) => {
      if (!sessionId || !container || !root || !rootPath) return;
      const path = node.key;
      if (dirCache[path] !== undefined) return;
      await dispatch(loadSandboxDir({ sessionId, container, root: rootPath, rootId: root, path }));
    },
    [dispatch, sessionId, container, root, rootPath, dirCache],
  );

  const handleSelect = useCallback(
    (key: string, node: TreeNode) => {
      dispatch(selectSandboxFile(key));
      if (node.isLeaf && sessionId && container && rootPath) {
        dispatch(loadSandboxContent({ sessionId, container, root: rootPath, path: key }));
      }
    },
    [dispatch, sessionId, container, rootPath],
  );

  const refresh = useCallback(() => {
    if (!sessionId) return;
    const expanded = expandedKeys.slice();
    dispatch(refreshSandbox());
    if (!container || !root || !rootPath) return;
    // Root level reloads via effect; reload previously expanded dirs too so the
    // tree returns to the same shape with fresh contents.
    dispatch(loadSandboxDir({ sessionId, container, root: rootPath, rootId: root, path: null }));
    for (const path of expanded) {
      dispatch(loadSandboxDir({ sessionId, container, root: rootPath, rootId: root, path }));
    }
  }, [dispatch, sessionId, container, root, rootPath, expandedKeys]);

  return {
    containers,
    containersLoaded,
    container,
    root,
    roots,
    treeData,
    expandedKeys,
    selectedPath,
    loading,
    error,
    starting,
    handleSelectContainer,
    handleSelectRoot,
    handleExpand,
    handleLoadData,
    handleSelect,
    refresh,
  };
}
