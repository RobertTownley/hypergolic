import { useCallback, useMemo, useState } from "react";
import { type FileTreeNode, collectDirPaths } from "./treeModel";

// Dirs start expanded; user toggles are XORed on top so collapsing an
// auto-expanded dir works and survives tree refreshes.
export function useExpandedDirs(trees: (FileTreeNode | null)[]): {
  expandedDirs: Set<string>;
  toggleDir: (path: string) => void;
} {
  const [toggled, setToggled] = useState<Set<string>>(new Set());

  const expandedDirs = useMemo(() => {
    const next = new Set<string>();
    for (const tree of trees) {
      if (tree) for (const p of collectDirPaths(tree)) next.add(p);
    }
    for (const p of toggled) {
      if (next.has(p)) next.delete(p);
      else next.add(p);
    }
    return next;
  }, [trees, toggled]);

  const toggleDir = useCallback((path: string) => {
    setToggled((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }, []);

  return { expandedDirs, toggleDir };
}
