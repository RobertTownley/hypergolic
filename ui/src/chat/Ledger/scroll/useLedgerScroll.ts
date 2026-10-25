import { useStickToBottom } from "./useStickToBottom";
import { useScrollShortcuts } from "./useScrollShortcuts";
import { useScrollToMessage } from "./useScrollToMessage";

export function useLedgerScroll(messageCount: number) {
  const { viewportRef, contentRef, showJumpToLatest, scrollToBottom, unpin } = useStickToBottom(messageCount);
  useScrollShortcuts(viewportRef, scrollToBottom, unpin);
  useScrollToMessage(viewportRef, unpin);
  return { viewportRef, contentRef, showJumpToLatest, scrollToBottom };
}
