import { formatTokens } from "@/shared/formatTokens";
import { contextOf, type UsageInfo } from "@/types/api";
import styles from "./MessageMeta.module.css";

interface MessageMetaProps {
  /** Sequence number (e.g. 5) or a range tuple [start, end] for grouped tool messages */
  sequence?: number | [number, number];
  /** Token usage; rendered only for assistant messages (caller decides) */
  usage?: UsageInfo | null;
  /** Context growth this turn caused (its tool results, measured at the next
   * call); when present the label breaks context into in/out. */
  inputDelta?: number | null;
  /** Pre-formatted timestamp string; rendered on the right */
  timestamp?: string | null;
}

function formatSequence(sequence: number | [number, number]): string {
  if (Array.isArray(sequence)) {
    const [start, end] = sequence;
    if (start === end) return `#${start}`;
    return `#${start}\u2013${end}`;
  }
  return `#${sequence}`;
}

/**
 * With an inputDelta the label reads as a ledger: total context, then what
 * this turn added — the input its results fed forward and its own output.
 */
function formatUsage(usage: UsageInfo, inputDelta?: number | null): string | null {
  const context = contextOf(usage);
  if (context <= 0 && usage.output_tokens <= 0) return null;
  const out = formatTokens(usage.output_tokens);
  if (inputDelta == null) return `${formatTokens(context)} \u2192 ${out} tok`;
  return `${formatTokens(context)} \u2192 ${formatTokens(inputDelta)} in, ${out} out tok`;
}

export function MessageMeta({ sequence, usage, inputDelta, timestamp }: MessageMetaProps) {
  const usageLabel = usage ? formatUsage(usage, inputDelta) : null;
  const hasLeft = sequence !== undefined || usageLabel !== null;
  const hasRight = timestamp != null && timestamp !== "";

  if (!hasLeft && !hasRight) return null;

  return (
    <>
      {hasLeft && (
        <span className={styles.left} data-testid="message-meta-left">
          {sequence !== undefined && <span>{formatSequence(sequence)}</span>}
          {usageLabel !== null && <span>{usageLabel}</span>}
        </span>
      )}
      {hasRight && (
        <span className={styles.right} data-testid="message-meta-right">
          {timestamp}
        </span>
      )}
    </>
  );
}
