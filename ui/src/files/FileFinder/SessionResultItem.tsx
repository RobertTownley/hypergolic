import { MessageSquareIcon } from "lucide-react";
import type { SessionSearchMatch } from "./types";
import styles from "./FileFinder.module.css";

export function SessionResultItem({
  match,
  selected,
  onClick,
  onMouseEnter,
}: {
  match: SessionSearchMatch;
  selected: boolean;
  onClick: () => void;
  onMouseEnter: () => void;
}) {
  const date = new Date(match.updated_at).toLocaleDateString();
  const label = match.first_message
    ? match.first_message.slice(0, 60) + (match.first_message.length > 60 ? "\u2026" : "")
    : "Session";

  return (
    <div
      className={`${styles.resultItem} ${selected ? styles.resultItemSelected : ""}`}
      onClick={onClick}
      onMouseEnter={onMouseEnter}
    >
      <MessageSquareIcon className={styles.resultIcon} />
      <div className={styles.resultInfo}>
        <span className={styles.resultName}>
          {label}
          <span className={styles.resultPath}>{" "}{match.project_name} · {date}</span>
        </span>
        <span className={styles.resultLineMatch}>
          <span className={styles.resultLineNumber}>{match.match_role}</span>
          {match.match_text.slice(0, 120)}
        </span>
      </div>
      <span className={`${styles.resultTypeTag} ${styles.tagSession}`}>session</span>
    </div>
  );
}
