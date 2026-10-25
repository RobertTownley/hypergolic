import { useEffect, useRef, useState } from "react";
import { ChevronDownIcon, GitBranchIcon, LoaderCircleIcon, PlusIcon } from "lucide-react";
import styles from "./BranchSelect.module.css";

export interface BranchSelectProps {
  branches: string[];
  value: string | null | undefined;
  onSelect: (branch: string) => void;
  onCreate?: (name: string) => void;
  loading?: boolean;
  disabled?: boolean;
  placeholder?: string;
  inline?: boolean;
  className?: string;
}

export function BranchSelect({
  branches,
  value,
  onSelect,
  onCreate,
  loading = false,
  disabled = false,
  placeholder = "Select branch",
  inline = false,
  className,
}: BranchSelectProps) {
  const [open, setOpen] = useState(false);
  const [creatingNew, setCreatingNew] = useState(false);
  const [newName, setNewName] = useState("");
  const [filter, setFilter] = useState("");

  const containerRef = useRef<HTMLDivElement>(null);
  const newInputRef = useRef<HTMLInputElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (creatingNew) newInputRef.current?.focus();
  }, [creatingNew]);

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        closeDropdown();
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  function closeDropdown() {
    setOpen(false);
    setCreatingNew(false);
    setNewName("");
    setFilter("");
  }

  function submitNew() {
    const name = newName.trim();
    if (!name || !onCreate) return;
    closeDropdown();
    onCreate(name);
  }

  const filtered = filter
    ? branches.filter((b) => b.toLowerCase().includes(filter.toLowerCase()))
    : branches;

  const triggerLabel = value ?? placeholder;
  const dropdownClass = inline ? styles.dropdownInline : styles.dropdown;

  return (
    <div
      className={`${styles.wrapper}${className ? " " + className : ""}`}
      ref={containerRef}
    >
      <button
        type="button"
        className={styles.trigger}
        onClick={() => {
          if (disabled || loading) return;
          if (open) { closeDropdown(); } else {
            setOpen(true);
            requestAnimationFrame(() => searchRef.current?.focus());
          }
        }}
        disabled={disabled || loading}
        title="Switch branch"
      >
        {loading ? (
          <LoaderCircleIcon className={`icon-spin ${styles.spinner}`} />
        ) : (
          <span className={styles.value}>{triggerLabel}</span>
        )}
        <ChevronDownIcon className={styles.caret} />
      </button>

      {open && (
        <div className={dropdownClass}>
          <input
            ref={searchRef}
            className={styles.search}
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter branches…"
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.preventDefault();
                e.stopPropagation();
                closeDropdown();
              }
              if (e.key === "Enter" && filtered.length === 1) {
                e.preventDefault();
                closeDropdown();
                onSelect(filtered[0]);
              }
            }}
          />

          {onCreate && (
            <>
              {creatingNew ? (
                <div className={styles.newRow}>
                  <input
                    ref={newInputRef}
                    className={styles.newInput}
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        submitNew();
                      }
                      if (e.key === "Escape") {
                        e.preventDefault();
                        e.stopPropagation();
                        setCreatingNew(false);
                      }
                    }}
                    placeholder="branch-name"
                  />
                  <button
                    type="button"
                    className={styles.newConfirm}
                    onClick={submitNew}
                    disabled={!newName.trim()}
                    title="Create branch"
                  >
                    <PlusIcon />
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  className={styles.item}
                  onClick={() => setCreatingNew(true)}
                >
                  <PlusIcon className={styles.itemIcon} />
                  New branch
                </button>
              )}
              <div className={styles.divider} />
            </>
          )}

          {filtered.length === 0 ? (
            <span className={styles.empty}>No branches match</span>
          ) : (
            filtered.map((b) => (
              <button
                key={b}
                type="button"
                className={`${styles.item}${b === value ? " " + styles.itemActive : ""}`}
                onClick={() => {
                  closeDropdown();
                  onSelect(b);
                }}
              >
                <GitBranchIcon className={styles.itemIcon} />
                {b}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
