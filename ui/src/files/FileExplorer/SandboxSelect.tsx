import { useEffect, useRef, useState } from "react";
import { ChevronDownIcon } from "lucide-react";
import styles from "./FileExplorer.module.css";

interface SandboxSelectOption {
  value: string;
  label: string;
}

interface SandboxSelectProps {
  options: SandboxSelectOption[];
  value: string | null;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  ariaLabel?: string;
}

export function SandboxSelect({
  options,
  value,
  onChange,
  placeholder = "Select",
  disabled = false,
  ariaLabel,
}: SandboxSelectProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const selected = options.find((o) => o.value === value) ?? null;

  return (
    <div className={styles.selectWrapper} ref={ref}>
      <button
        type="button"
        className={styles.selectTrigger}
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => !disabled && setOpen((o) => !o)}
      >
        <span className={styles.selectValue}>{selected?.label ?? placeholder}</span>
        <ChevronDownIcon className={styles.selectCaret} />
      </button>
      {open && (
        <div className={styles.selectDropdown} role="listbox">
          {options.length === 0 ? (
            <span className={styles.selectEmpty}>No options</span>
          ) : (
            options.map((o) => (
              <button
                key={o.value}
                type="button"
                role="option"
                aria-selected={o.value === value}
                className={`${styles.selectItem}${o.value === value ? " " + styles.selectItemActive : ""}`}
                onClick={() => {
                  setOpen(false);
                  onChange(o.value);
                }}
              >
                {o.label}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
