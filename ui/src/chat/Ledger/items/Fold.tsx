import { memo, useState } from "react";
import { ChevronRightIcon } from "lucide-react";
import { formatTokens } from "@/shared/formatTokens";
import type { FoldItem } from "../quietRuns";
import { Turn } from "./Turn";
import { cx } from "@/utils/cx";
import styles from "./items.module.css";

const plural = (n: number, noun: string) => `${n} ${noun}${n === 1 ? "" : "s"}`;

function summaryOf(item: FoldItem): string {
  const parts: string[] = [];
  if (item.calls > 0) parts.push(plural(item.calls, "tool call"));
  if (item.thinking > 0) parts.push(plural(item.thinking, "thinking block"));
  return parts.join(" + ");
}

function tokensOf(item: FoldItem): string | null {
  if (item.contextGrowth != null) {
    return `${formatTokens(item.contextGrowth)} in, ${formatTokens(item.outputTokens)} out tok`;
  }
  return item.outputTokens > 0 ? `${formatTokens(item.outputTokens)} out tok` : null;
}

/**
 * A run of quiet turns — tool calls and thinking with no prose or images —
 * folded to one line. Expanding restores the underlying turns in place.
 */
export const Fold = memo(function Fold({ item }: { item: FoldItem }) {
  const [open, setOpen] = useState(false);
  const tokens = tokensOf(item);

  const note = (
    <button
      type="button"
      className={cx(styles.fold, open && styles.foldOpen)}
      aria-expanded={open}
      onClick={() => setOpen(!open)}
    >
      <ChevronRightIcon className={styles.foldCaret} />
      {item.sequence && <span>{`#${item.sequence[0]}\u2013${item.sequence[1]}`}</span>}
      <span>{summaryOf(item)}</span>
      {tokens && <span className={styles.foldMeta}>{tokens}</span>}
    </button>
  );

  if (!open) return note;
  return (
    <>
      {note}
      {item.turns.map((t) => (
        <Turn
          key={t.key}
          messageId={t.messageId}
          thinking={t.thinking}
          text={t.text}
          calls={t.calls}
          truncated={t.truncated}
          isError={t.isError}
          createdAt={t.createdAt}
          sequence={t.sequence}
          usage={t.usage}
          inputDelta={t.inputDelta}
        />
      ))}
    </>
  );
});
