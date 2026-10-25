import { useEffect, type RefObject } from "react";
import { SCROLL_TO_MESSAGE_EVENT } from "@/activity/constants";

const HIGHLIGHT_MS = 1500;

export function useScrollToMessage(viewportRef: RefObject<HTMLDivElement | null>, unpin: () => void) {
  useEffect(() => {
    const handler = (event: Event) => {
      const { messageId } = (event as CustomEvent).detail;
      requestAnimationFrame(() => {
        const container = viewportRef.current;
        const target = container?.querySelector<HTMLElement>(`[data-message-id="${messageId}"]`);
        if (!container || !target) return;
        unpin();
        centre(container, target);
        flash(target);
      });
    };
    window.addEventListener(SCROLL_TO_MESSAGE_EVENT, handler);
    return () => window.removeEventListener(SCROLL_TO_MESSAGE_EVENT, handler);
  }, [viewportRef, unpin]);
}

function centre(container: HTMLElement, target: HTMLElement) {
  const top = target.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop;
  container.scrollTo({
    top: Math.max(0, top - container.clientHeight / 2 + target.offsetHeight / 2),
    behavior: "smooth",
  });
}

function flash(target: HTMLElement) {
  target.classList.remove("highlight-flash");
  void target.offsetWidth;
  target.classList.add("highlight-flash");
  setTimeout(() => target.classList.remove("highlight-flash"), HIGHLIGHT_MS);
}
