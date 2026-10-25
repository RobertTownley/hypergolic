import { memo } from "react";
import { useAppSelector } from "@/store";
import { Chip, Base64Image } from "@/shared/components";
import { useInspectorSync, useLedgerContext } from "../LedgerContext";
import { firstLines, formatBytes, splitStderr } from "../callPreview";
import { renderAnsi } from "../ansi";
import { StatusChip } from "./StatusChip";
import { Stderr, CARD_STDERR_LINES } from "./Stderr";
import type { LedgerCall } from "../ledgerModel";
import { cx } from "@/utils/cx";
import styles from "./items.module.css";

/** Output lines shown inline. Beyond this the footer offers the inspector. */
const OUTPUT_LINES = 12;
/** Failures get more room: the reason is usually a few lines into the trace. */
const ERROR_OUTPUT_LINES = 20;
/** Output past this is worth flagging — cheap to print, expensive to read. */
const BLOATED_LINES = 200;

function lastLines(text: string, count: number): string {
  const lines = text.replace(/\n$/, "").split("\n");
  return lines.slice(-count).join("\n");
}

/** A single invocation: the command line, what it printed, and how it ended. */
export const CallCard = memo(function CallCard({ call }: { call: LedgerCall }) {
  const { inspect, toggleInspect, inspected } = useLedgerContext();
  useInspectorSync(call);

  const liveOutput = useAppSelector((s) =>
    call.status === "pending" ? s.messages.liveToolOutputByToolUseId[call.id] : undefined,
  );
  const { output } = call;
  // A failure's stderr gets its own section so a long stdout cannot clip it
  // away: the reason the call failed is the one part the reader came for.
  const stdout = output.stderr ? splitStderr(output.text).stdout : output.text;
  const visibleLines = call.status === "error" ? ERROR_OUTPUT_LINES : OUTPUT_LINES;
  const stdoutLines = stdout ? stdout.split("\n").length : 0;
  const clipped = stdoutLines > visibleLines;
  const bloated = output.lines > BLOATED_LINES;
  const hasFooter = clipped || output.lines > 0;
  const open = inspected?.id === call.id;

  return (
    <div className={cx(styles.card, styles[call.status], open && styles.inspected)}>
      <button
        type="button"
        className={cx(styles.head, styles.cardHead)}
        aria-pressed={open}
        onClick={() => toggleInspect(call)}
      >
        <span className={styles.sigil}>{call.form === "command" ? "$" : "▸"}</span>
        {call.form !== "command" && <Chip tone="tool">{call.label}</Chip>}
        <span className={styles.preview}>{call.preview}</span>
        <StatusChip call={call} dots />
      </button>

      {call.status === "pending" ? (
        liveOutput ? (
          <div className={styles.section}>
            <pre className={styles.pre}>{renderAnsi(lastLines(liveOutput, OUTPUT_LINES))}</pre>
            <div className={styles.pendingRow}>
              <span className={styles.cursor} />
            </div>
          </div>
        ) : (
          <div className={styles.pendingRow}>
            {call.writing ? "writing input" : "waiting for output"}
            <span className={styles.cursor} />
          </div>
        )
      ) : (
        <>
          {stdout && (
            // Clipped by slicing the text, not by a max-height: a card's
            // geometry follows its line budget, never the payload's size.
            <div className={styles.section}>
              <pre className={styles.pre}>{renderAnsi(firstLines(stdout, visibleLines))}</pre>
            </div>
          )}
          {output.stderr && (
            <div className={styles.section}>
              <Stderr text={output.stderr} lines={CARD_STDERR_LINES} />
            </div>
          )}
          {output.images.length > 0 && (
            <div className={styles.shots}>
              {output.images.map((image, i) => (
                <Base64Image key={i} block={image} alt="Tool result" className={styles.shot} />
              ))}
            </div>
          )}
          {hasFooter && (
            <div className={styles.foot}>
              <span>
                {clipped ? `${visibleLines} of ${output.lines.toLocaleString()} lines` : `${output.lines} lines`}
                {` · ${formatBytes(output.chars)}`}
              </span>
              {bloated && <Chip tone="warning">bloated output</Chip>}
              <span className={styles.footSpacer} />
              <button type="button" className={styles.linkButton} onClick={() => inspect(call)}>
                open ↗
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
});
