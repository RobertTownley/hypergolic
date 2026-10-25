import styles from "./ApprovalShared.module.css";

interface ViewToggleProps {
  mode: "rendered" | "raw";
  onChange: (mode: "rendered" | "raw") => void;
}

export function ViewToggle({ mode, onChange }: ViewToggleProps) {
  return (
    <div className={styles.viewToggle} role="group" aria-label="View mode">
      <button
        type="button"
        className={`${styles.viewToggleButton} ${mode === "rendered" ? styles.viewToggleButtonActive : ""}`}
        onClick={() => onChange("rendered")}
        aria-pressed={mode === "rendered"}
      >
        Rendered
      </button>
      <button
        type="button"
        className={`${styles.viewToggleButton} ${mode === "raw" ? styles.viewToggleButtonActive : ""}`}
        onClick={() => onChange("raw")}
        aria-pressed={mode === "raw"}
      >
        Raw JSON
      </button>
    </div>
  );
}
