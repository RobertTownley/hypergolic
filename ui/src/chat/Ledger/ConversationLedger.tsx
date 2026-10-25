import { memo, type ReactNode, type RefObject } from "react";
import { ArrowDownIcon } from "lucide-react";
import { useAppSelector } from "@/store";
import { selectLedgerItems } from "./conversationView";
import type { ViewItem } from "./quietRuns";
import { Say } from "./items/Say";
import { Turn } from "./items/Turn";
import { Fold } from "./items/Fold";
import { Summary } from "./items/Summary";
import { Transition } from "./items/Transition";
import { Activation } from "./items/Activation";
import styles from "./Ledger.module.css";

interface ConversationLedgerProps {
  sessionId: string;
  viewportRef: RefObject<HTMLDivElement | null>;
  contentRef: RefObject<HTMLDivElement | null>;
  showJumpToLatest: boolean;
  onJumpToLatest: () => void;
  /** The live turn, errors, empty state — anything pinned below the transcript. */
  children?: ReactNode;
}

/**
 * The conversation, as one scroll container with one column of items.
 *
 * The only element that scrolls is the viewport: every row inside it is either
 * a fixed height or a ScrollBox with its own bounded height, so appending a
 * huge tool result moves the scroll position by tens of pixels rather than
 * thousands. That property is what makes pinning to the bottom feel stable.
 */
export function ConversationLedger({
  sessionId,
  viewportRef,
  contentRef,
  showJumpToLatest,
  onJumpToLatest,
  children,
}: ConversationLedgerProps) {
  const items = useAppSelector((s) => selectLedgerItems(s, sessionId));
  return (
    <div className={styles.viewport} ref={viewportRef}>
      <div className={styles.lane} ref={contentRef}>
        <Transcript items={items} />
        {children}
      </div>
      {showJumpToLatest && (
        <button type="button" className={styles.jump} onClick={onJumpToLatest}>
          <ArrowDownIcon /> New messages
        </button>
      )}
    </div>
  );
}

/**
 * Memoized on the items array, which the view-model selector keeps stable
 * across streaming deltas: a token arriving must not re-render the finished
 * transcript.
 */
const Transcript = memo(function Transcript({ items }: { items: ViewItem[] }) {
  return (
    <>
      {items.map((item) => {
        if (item.kind === "fold") {
          return <Fold key={item.key} item={item} />;
        }
        if (item.kind === "summary") {
          return <Summary key={item.key} item={item} />;
        }
        if (item.kind === "transition") {
          return (
            <Transition
              key={item.key}
              toolName={item.toolName}
              workflowName={item.workflowName}
              stateName={item.stateName}
            />
          );
        }
        if (item.kind === "activation") {
          return <Activation key={item.key} skill={item.skill} call={item.call} />;
        }
        if (item.kind === "say") {
          return (
            <Say
              key={item.key}
              message={item.message}
              variant={item.variant}
              sequence={item.sequence}
            />
          );
        }
        return (
          <Turn
            key={item.key}
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
      })}
    </>
  );
});
