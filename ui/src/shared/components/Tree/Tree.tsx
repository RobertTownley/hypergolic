import { useCallback, useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { ChevronDownIcon, FileIcon, FolderIcon, FolderOpenIcon } from "lucide-react";
import { Spinner } from "@/shared/components/Spinner";
import styles from "./Tree.module.css";

export interface TreeNode {
  key: string;
  title: ReactNode;
  icon?: ReactNode;
  isLeaf?: boolean;
  children?: TreeNode[];
}

interface TreeProps {
  treeData: TreeNode[];
  selectedKey?: string | null;
  onSelect?: (key: string, node: TreeNode) => void;
  expandedKeys: string[];
  onExpand: (keys: string[]) => void;
  /** Called once when a folder with no loaded children is expanded. */
  loadData?: (node: TreeNode) => Promise<unknown>;
  className?: string;
  "aria-label"?: string;
}

interface VisibleRow {
  node: TreeNode;
  level: number;
  parentKey: string | null;
}

function flatten(nodes: TreeNode[], expanded: Set<string>, level = 0, parentKey: string | null = null, out: VisibleRow[] = []) {
  for (const node of nodes) {
    out.push({ node, level, parentKey });
    if (!node.isLeaf && expanded.has(node.key) && node.children) {
      flatten(node.children, expanded, level + 1, node.key, out);
    }
  }
  return out;
}

/** A directory tree: clicking a folder selects and toggles it. */
export function Tree({
  treeData, selectedKey, onSelect, expandedKeys, onExpand, loadData, className, "aria-label": ariaLabel,
}: TreeProps) {
  const idPrefix = useId();
  const expanded = useMemo(() => new Set(expandedKeys), [expandedKeys]);
  const rows = useMemo(() => flatten(treeData, expanded), [treeData, expanded]);
  const [focusedKey, setFocusedKey] = useState<string | null>(null);
  const [loadingKeys, setLoadingKeys] = useState<Set<string>>(() => new Set());
  const loadedKeys = useRef(new Set<string>());

  const setOpen = useCallback((node: TreeNode, open: boolean) => {
    if (node.isLeaf || expanded.has(node.key) === open) return;
    onExpand(open ? [...expandedKeys, node.key] : expandedKeys.filter((k) => k !== node.key));
    if (open && loadData && !node.children?.length && !loadedKeys.current.has(node.key)) {
      loadedKeys.current.add(node.key);
      setLoadingKeys((s) => new Set(s).add(node.key));
      loadData(node).finally(() =>
        setLoadingKeys((s) => { const n = new Set(s); n.delete(node.key); return n; }),
      );
    }
  }, [expanded, expandedKeys, onExpand, loadData]);

  const activate = useCallback((node: TreeNode) => {
    setFocusedKey(node.key);
    onSelect?.(node.key, node);
    if (!node.isLeaf) setOpen(node, !expanded.has(node.key));
  }, [onSelect, setOpen, expanded]);

  const focusIndex = rows.findIndex((r) => r.node.key === (focusedKey ?? selectedKey));
  const moveFocus = (index: number) => {
    const row = rows[Math.max(0, Math.min(rows.length - 1, index))];
    if (!row) return;
    setFocusedKey(row.node.key);
    document.getElementById(`${idPrefix}-${row.node.key}`)?.scrollIntoView({ block: "nearest" });
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    const row = rows[focusIndex];
    switch (e.key) {
      case "ArrowDown": moveFocus(focusIndex + 1); break;
      case "ArrowUp": moveFocus(focusIndex < 0 ? 0 : focusIndex - 1); break;
      case "Home": moveFocus(0); break;
      case "End": moveFocus(rows.length - 1); break;
      case "ArrowRight":
        if (!row || row.node.isLeaf) break;
        if (!expanded.has(row.node.key)) setOpen(row.node, true);
        else moveFocus(focusIndex + 1);
        break;
      case "ArrowLeft":
        if (!row) break;
        if (!row.node.isLeaf && expanded.has(row.node.key)) setOpen(row.node, false);
        else if (row.parentKey) moveFocus(rows.findIndex((r) => r.node.key === row.parentKey));
        break;
      case "Enter":
      case " ":
        if (row) activate(row.node);
        break;
      default:
        return;
    }
    e.preventDefault();
  };

  const activeRow = rows[focusIndex];

  return (
    <div
      role="tree"
      aria-label={ariaLabel}
      tabIndex={0}
      aria-activedescendant={activeRow ? `${idPrefix}-${activeRow.node.key}` : undefined}
      className={`${styles.tree} ${className ?? ""}`}
      onKeyDown={handleKeyDown}
    >
      {rows.map(({ node, level }) => {
        const isOpen = expanded.has(node.key);
        const isSelected = node.key === selectedKey;
        const isFocused = node.key === activeRow?.node.key;
        const icon = node.icon ?? (node.isLeaf ? <FileIcon /> : isOpen ? <FolderOpenIcon /> : <FolderIcon />);
        return (
          <div
            key={node.key}
            id={`${idPrefix}-${node.key}`}
            role="treeitem"
            aria-level={level + 1}
            aria-selected={isSelected}
            aria-expanded={node.isLeaf ? undefined : isOpen}
            className={`${styles.row} ${isSelected ? styles.selected : ""} ${isFocused ? styles.focused : ""}`}
            style={{ paddingLeft: level * 12 }}
            onClick={() => activate(node)}
          >
            <span
              className={styles.switcher}
              onClick={(e) => { e.stopPropagation(); setFocusedKey(node.key); setOpen(node, !isOpen); }}
            >
              {node.isLeaf ? null : loadingKeys.has(node.key) ? (
                <Spinner size="small" className={styles.loading} />
              ) : (
                <ChevronDownIcon className={isOpen ? undefined : styles.closed} />
              )}
            </span>
            <span className={styles.icon}>{icon}</span>
            <span className={styles.title}>{node.title}</span>
          </div>
        );
      })}
    </div>
  );
}
