import { useEffect, type RefObject } from "react";
import {
  SCROLL_CONVO_UP_EVENT,
  SCROLL_CONVO_DOWN_EVENT,
  SCROLL_CONVO_TOP_EVENT,
  SCROLL_CONVO_BOTTOM_EVENT,
} from "@/hooks/useKeyboardShortcuts";

const SCROLL_STEP = 400;

export function useScrollShortcuts(
  viewportRef: RefObject<HTMLDivElement | null>,
  scrollToBottom: () => void,
  unpin: () => void,
) {
  useEffect(() => {
    const smooth = (fn: (el: HTMLDivElement) => void, up: boolean) => () => {
      if (up) unpin();
      if (viewportRef.current) fn(viewportRef.current);
    };
    const handlers: [string, () => void][] = [
      [SCROLL_CONVO_UP_EVENT, smooth((el) => el.scrollBy({ top: -SCROLL_STEP, behavior: "smooth" }), true)],
      [SCROLL_CONVO_DOWN_EVENT, smooth((el) => el.scrollBy({ top: SCROLL_STEP, behavior: "smooth" }), false)],
      [SCROLL_CONVO_TOP_EVENT, smooth((el) => el.scrollTo({ top: 0, behavior: "smooth" }), true)],
      [SCROLL_CONVO_BOTTOM_EVENT, scrollToBottom],
    ];
    handlers.forEach(([name, fn]) => window.addEventListener(name, fn));
    return () => handlers.forEach(([name, fn]) => window.removeEventListener(name, fn));
  }, [viewportRef, scrollToBottom, unpin]);
}
