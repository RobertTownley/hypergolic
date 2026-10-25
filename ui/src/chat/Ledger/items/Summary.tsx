import { memo, useCallback, useState } from "react";
import { ChevronRightIcon, PaperclipIcon, ShrinkIcon } from "lucide-react";
import { useAppDispatch, useAppSelector } from "@/store";
import { selectMessagesForSession } from "@/store/selectors";
import { addDraftSummaryRecall, selectDraft } from "@/store/uiSlice";
import { FOCUS_CHAT_EVENT } from "@/hooks/useKeyboardShortcuts";
import { serializeCompactedRun } from "../summaryRecall";
import { MarkdownContent } from "@/chat/MarkdownContent";
import type { LedgerItem } from "../ledgerModel";
import { Say } from "./Say";
import { Turn } from "./Turn";
import { Artifacts } from "./Artifacts";
import { cx } from "@/utils/cx";
import styles from "./items.module.css";

type SummaryItem = Extract<LedgerItem, { kind: "summary" }>;

function Detail({ item }: { item: LedgerItem }) {
  if (item.kind === "turn") {
    return (
      <Turn
        messageId={item.messageId}
        thinking={item.thinking}
        text={item.text}
        calls={item.calls}
        truncated={item.truncated}
        isError={item.isError}
        createdAt={item.createdAt}
        sequence={item.sequence}
        usage={item.usage}
        inputDelta={item.inputDelta}
        artifacts={item.artifacts}
      />
    );
  }
  if (item.kind === "say") {
    return <Say message={item.message} variant={item.variant} sequence={item.sequence} />;
  }
  return null;
}

/**
 * A per-turn compaction summary: the model sees this text instead of the
 * turn's tool calls and results, which stay expandable for the reader.
 */
function useRecall(summaryId: string): { staged: boolean; recall: () => void } {
  const dispatch = useAppDispatch();
  const sessionId = useAppSelector((s) => s.sessions.activeSessionId);
  const messages = useAppSelector((s) => (sessionId ? selectMessagesForSession(s, sessionId) : null));
  const staged = useAppSelector((s) =>
    sessionId
      ? selectDraft(s, sessionId).summaryRecalls.some((a) => a.summaryId === summaryId)
      : false,
  );
  const recall = useCallback(() => {
    if (!sessionId || !messages) return;
    const content = serializeCompactedRun(messages, summaryId);
    if (!content) return;
    dispatch(addDraftSummaryRecall({ sessionId, summaryId, content }));
    window.dispatchEvent(new Event(FOCUS_CHAT_EVENT));
  }, [dispatch, sessionId, messages, summaryId]);
  return { staged, recall };
}

export const Summary = memo(function Summary({ item }: { item: SummaryItem }) {
  const [open, setOpen] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const { staged, recall } = useRecall(item.key);
  return (
    <div className={cx(styles.summaryNote, open && styles.summaryOpen)}>
      <div className={styles.summaryHeader}>
        <button
          type="button"
          className={cx(styles.summaryToggle, open && styles.foldOpen)}
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          <ChevronRightIcon className={styles.foldCaret} />
          <ShrinkIcon />
          {open ? "Hide" : "Show"} summarized content
        </button>
        <button
          type="button"
          className={styles.summaryRecall}
          onClick={recall}
          disabled={staged}
          title="Attach the original, unsummarized content to your next message"
        >
          <PaperclipIcon /> {staged ? "attached to next message" : "re-include in next message"}
        </button>
      </div>
      <Artifacts images={item.artifacts} />
      {open && (
        <>
          <MarkdownContent text={item.text} />
          {item.details.length > 0 && (
            <button
              type="button"
              className={cx(styles.fold, showDetails && styles.foldOpen)}
              aria-expanded={showDetails}
              onClick={() => setShowDetails(!showDetails)}
            >
              <ChevronRightIcon className={styles.foldCaret} />
              <span>
                {showDetails ? "Hide" : "Show"} the {item.details.length} summarized messages
              </span>
              <span className={styles.foldMeta}>no longer sent to the model</span>
            </button>
          )}
          {showDetails && item.details.map((d) => <Detail key={d.key} item={d} />)}
        </>
      )}
    </div>
  );
});
