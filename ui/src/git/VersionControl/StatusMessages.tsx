import { XIcon } from "lucide-react";
import styles from "./VersionControl.module.css";

export function StatusMessages({
  error,
  actionOutput,
  onDismissError,
}: {
  error: string | null;
  actionOutput: string | null;
  onDismissError?: () => void;
}) {
  return (
    <>
      {error && (
        <div className={styles.errorOutput}>
          <div className={styles.errorOutputHeader}>
            <span className={styles.errorLabel}>Error</span>
            {onDismissError && (
              <button className={styles.dismissBtn} onClick={onDismissError}>
                <XIcon />
              </button>
            )}
          </div>
          <div className={styles.errorOutputText}>{error}</div>
        </div>
      )}
      {actionOutput && (
        <div className={styles.actionOutput}>
          <div className={styles.actionOutputText}>{actionOutput}</div>
        </div>
      )}
    </>
  );
}
