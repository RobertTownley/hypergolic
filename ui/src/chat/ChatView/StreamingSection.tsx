import { useAppSelector } from "@/store";
import { selectIsSessionStreaming, selectStreamingBlocksForSession } from "@/store/selectors";
import { LiveTurn } from "@/chat/Ledger";
import { StreamingIndicator } from "./StreamingIndicator";
import styles from "./ChatView.module.css";

interface StreamingSectionProps {
  sessionId: string;
  isTruncating: boolean;
  isRetrying: boolean;
}

// Owns the only subscription to streaming blocks. Streaming deltas update
// this array on every token, so any component that selects it re-renders
// per token — keeping the subscription here means a delta re-renders this
// leaf, not ChatView and the finished transcript above it.
export function StreamingSection({ sessionId, isTruncating, isRetrying }: StreamingSectionProps) {
  const streaming = useAppSelector((s) => selectIsSessionStreaming(s, sessionId));
  const blocks = useAppSelector((s) => selectStreamingBlocksForSession(s, sessionId));

  if (!streaming) return null;
  const mode = isRetrying ? "retrying" : isTruncating ? "truncating" : "thinking";
  if (blocks.length === 0) return <StreamingIndicator mode={mode} />;
  return (
    <>
      <LiveTurn blocks={blocks} />
      {isRetrying ? <StreamingIndicator mode="retrying" /> : <div className={styles.activeBar} />}
    </>
  );
}
