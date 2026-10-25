import { FileIcon, SearchIcon } from "lucide-react";
type FileSearchMatch = { path: string; line: number | null; text: string | null };
import styles from "./FileFinder.module.css";

export function ResultItem({
  match,
  selected,
  onClick,
  onMouseEnter,
}: {
  match: FileSearchMatch;
  selected: boolean;
  onClick: () => void;
  onMouseEnter: () => void;
}) {
  const isContentMatch = match.line != null;
  const parts = match.path.split("/");
  const fileName = parts.pop() ?? match.path;
  const dirPath = parts.join("/");

  return (
    <div
      className={`${styles.resultItem} ${selected ? styles.resultItemSelected : ""}`}
      onClick={onClick}
      onMouseEnter={onMouseEnter}
    >
      {isContentMatch
        ? <SearchIcon className={styles.resultIcon} />
        : <FileIcon className={styles.resultIcon} />
      }
      <div className={styles.resultInfo}>
        <span className={styles.resultName}>
          {fileName}
          {dirPath && <span className={styles.resultPath}>{" "}{dirPath}</span>}
        </span>
        {isContentMatch && match.text && (
          <span className={styles.resultLineMatch}>
            <span className={styles.resultLineNumber}>{match.line}</span>
            {match.text}
          </span>
        )}
      </div>
      <span className={`${styles.resultTypeTag} ${isContentMatch ? styles.tagContent : styles.tagFile}`}>
        {isContentMatch ? "content" : "file"}
      </span>
    </div>
  );
}
