import type { FileSource } from "@/store/workspace/state";
import styles from "./FileExplorer.module.css";

interface SourceToggleProps {
  value: FileSource;
  onChange: (source: FileSource) => void;
}

const OPTIONS: { value: FileSource; label: string }[] = [
  { value: "host", label: "Host" },
  { value: "sandbox", label: "Session Sandbox" },
];

export function SourceToggle({ value, onChange }: SourceToggleProps) {
  return (
    <div className={styles.sourceToggle} role="tablist" aria-label="File source">
      {OPTIONS.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            role="tab"
            aria-selected={active}
            className={active ? styles.sourceActive : styles.sourceBtn}
            onClick={() => onChange(opt.value)}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
