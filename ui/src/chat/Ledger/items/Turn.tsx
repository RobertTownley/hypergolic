import { memo, useState } from "react";
import { ChevronRightIcon } from "lucide-react";
import { Chip, MessageMeta } from "@/shared/components";
import { MarkdownContent } from "@/chat/MarkdownContent";
import { formatTimestamp } from "@/utils/formatTimestamp";
import type { LedgerCall } from "../ledgerModel";
import type { ContentBlock, UsageInfo } from "@/types/api";
import { Artifacts } from "./Artifacts";
import { CallCard } from "./CallCard";
import { CallRow } from "./CallRow";
import { SubagentCard } from "./SubagentCard";
import { Think } from "./Think";
import { cx } from "@/utils/cx";
import styles from "./items.module.css";

/** Subagent answers are prose meant to be read, so they never fold to a row. */
export function Call({ call, rich = true }: { call: LedgerCall; rich?: boolean }) {
  if (call.form === "subagent") return <SubagentCard call={call} />;
  return rich ? <CallCard call={call} /> : <CallRow call={call} />;
}

interface TurnProps {
  messageId?: string;
  thinking: string[];
  text: string[];
  calls: LedgerCall[];
  truncated?: boolean;
  isError?: boolean;
  createdAt?: string;
  sequence?: number | [number, number];
  usage?: UsageInfo | null;
  inputDelta?: number | null;
  artifacts?: ContentBlock[];
}

/**
 * One assistant turn. Reasoning, prose and calls are facets of a single
 * message, so they share one row, one meta line and one truncation state.
 * Prose always renders in full — it is the story. Calls are evidence: folded
 * to one line each until the turn is expanded or a row is inspected.
 */
export const Turn = memo(function Turn({
  messageId,
  thinking,
  text,
  calls,
  truncated,
  isError,
  createdAt,
  sequence,
  usage,
  inputDelta,
  artifacts,
}: TurnProps) {
  const timestamp = createdAt ? formatTimestamp(createdAt) : null;
  // Every turn opens as rows, the latest too: a turn that changed form when the
  // next one landed would move the page above where the reader is.
  const [expanded, setExpanded] = useState(false);
  const foldable = calls.some((c) => c.form !== "subagent");

  return (
    <div
      data-message-id={messageId}
      className={cx(styles.turn, truncated && styles.truncated)}
    >
      {truncated && <Chip className={styles.truncatedBadge}>truncated</Chip>}
      <MessageMeta sequence={sequence} usage={usage} inputDelta={inputDelta} timestamp={timestamp} />
      {foldable && (
        <button
          type="button"
          className={cx(styles.turnCaret, expanded && styles.caretOpen)}
          aria-label={expanded ? "Fold calls" : "Expand calls"}
          onClick={() => setExpanded(!expanded)}
        >
          <ChevronRightIcon />
        </button>
      )}
      {thinking.map((t, i) => (
        <Think key={`think-${i}`} text={t} />
      ))}
      {text.length > 0 && (
        <div data-agent-prose className={cx(styles.prose, isError && styles.errorProse)}>
          {text.map((t, i) => (
            <MarkdownContent key={`text-${i}`} text={t} />
          ))}
        </div>
      )}
      {calls.length > 0 && (
        <div className={styles.stack}>
          {calls.map((call) => (
            <Call key={call.id} call={call} rich={expanded} />
          ))}
        </div>
      )}
      <Artifacts images={artifacts} />
    </div>
  );
});
