import { renderAnsi } from "../ansi";
import { firstLines } from "../callPreview";
import { cx } from "@/utils/cx";
import styles from "./items.module.css";

/** Lines of stderr shown under a folded row — the headline of the failure. */
export const ROW_STDERR_LINES = 3;
/** Lines of stderr the expanded card shows; past this the inspector has it. */
export const CARD_STDERR_LINES = 12;

/**
 * What a failed command wrote to stderr, lifted out of the result so the
 * reader sees the failure without opening the inspector. The agent may have
 * recovered on the next call, but the miss is still worth a glance.
 */
export function Stderr({ text, lines, className }: { text: string; lines: number; className?: string }) {
  const total = text.split("\n").length;
  const clipped = total > lines;
  return (
    <div className={cx(styles.stderr, className)} data-testid="stderr">
      <span className={styles.stderrTag}>stderr</span>
      <pre className={styles.stderrPre}>{renderAnsi(firstLines(text, lines))}</pre>
      {clipped && <span className={styles.stderrMore}>{`+${(total - lines).toLocaleString()} lines`}</span>}
    </div>
  );
}
