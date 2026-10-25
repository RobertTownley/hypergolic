import { memo } from "react";
import { Chip, Base64Image } from "@/shared/components";
import { useInspectorSync, useLedgerContext } from "../LedgerContext";
import { formatBytes } from "../callPreview";
import { StatusChip } from "./StatusChip";
import { Stderr, ROW_STDERR_LINES } from "./Stderr";
import type { LedgerCall } from "../ledgerModel";
import { cx } from "@/utils/cx";
import styles from "./items.module.css";

/** A call folded to one line: the invocation, its size, how it ended. */
export const CallRow = memo(function CallRow({ call }: { call: LedgerCall }) {
  const { toggleInspect, inspected } = useLedgerContext();
  useInspectorSync(call);
  const open = inspected?.id === call.id;

  const row = (
    <button
      type="button"
      className={cx(styles.row, styles[call.status], open && styles.inspected)}
      aria-pressed={open}
      onClick={() => toggleInspect(call)}
    >
      <span className={styles.sigil}>{call.form === "command" ? "$" : "▸"}</span>
      {call.form !== "command" && <Chip tone="tool">{call.label}</Chip>}
      <span className={styles.headline}>{call.headline}</span>
      {call.output.lines > 0 && (
        <span className={styles.rowMeta}>
          {`${call.output.lines.toLocaleString()} lines · ${formatBytes(call.output.chars)}`}
        </span>
      )}
      <StatusChip call={call} />
    </button>
  );

  const { stderr, images } = call.output;
  if (!stderr && images.length === 0) return row;
  return (
    <div>
      {row}
      {stderr && <Stderr text={stderr} lines={ROW_STDERR_LINES} className={styles.rowStderr} />}
      {images.length > 0 && (
        <div className={styles.thumbs}>
          {images.map((image, i) => (
            <Base64Image key={i} block={image} alt="Tool result" className={styles.thumb} />
          ))}
        </div>
      )}
    </div>
  );
});
