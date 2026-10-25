import styles from "./FileFinder.module.css";

export function TogglePill({
  label,
  shortcut,
  active,
  onClick,
}: {
  label: string;
  shortcut: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <span
      className={`${styles.togglePill} ${active ? styles.togglePillActive : styles.togglePillInactive}`}
      onClick={onClick}
    >
      {label}
      <span className={styles.kbd}>{shortcut}</span>
    </span>
  );
}
