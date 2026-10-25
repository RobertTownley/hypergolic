import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { scrollerAbove } from "./scrollerAbove";

const REPIN_SLACK_PX = 100;
const UP_KEYS = new Set(["ArrowUp", "PageUp", "Home"]);

export function useStickToBottom(messageCount: number) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const pinnedRef = useRef(true);
  const [showJumpToLatest, setShowJumpToLatest] = useState(false);
  const seenCountRef = useRef(messageCount);

  const pin = useCallback(() => {
    pinnedRef.current = true;
    setShowJumpToLatest(false);
  }, []);

  const unpin = useCallback(() => {
    pinnedRef.current = false;
  }, []);

  const scrollToBottom = useCallback(() => {
    pin();
    const el = viewportRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [pin]);

  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    let lastTop = el.scrollTop;
    let dragging = false;

    const onScroll = () => {
      const up = el.scrollTop < lastTop;
      lastTop = el.scrollTop;
      if (up && dragging) unpin();
      else if (!up && el.scrollHeight - el.scrollTop - el.clientHeight <= REPIN_SLACK_PX) pin();
    };
    const onWheel = (e: WheelEvent) => {
      if (e.deltaY < 0 && el.scrollTop > 0 && !scrollerAbove(e.target, el)) unpin();
    };
    const onKey = (e: KeyboardEvent) => {
      if (el.scrollTop > 0 && (UP_KEYS.has(e.key) || (e.key === " " && e.shiftKey))) unpin();
    };
    const onDown = (e: PointerEvent) => (dragging = e.target === el);
    const onUp = () => (dragging = false);
    const observer = new ResizeObserver(() => {
      if (pinnedRef.current) el.scrollTop = el.scrollHeight;
    });

    el.addEventListener("scroll", onScroll, { passive: true });
    el.addEventListener("wheel", onWheel, { passive: true });
    el.addEventListener("keydown", onKey);
    el.addEventListener("pointerdown", onDown);
    window.addEventListener("pointerup", onUp);
    observer.observe(el);
    if (contentRef.current) observer.observe(contentRef.current);
    return () => {
      el.removeEventListener("scroll", onScroll);
      el.removeEventListener("wheel", onWheel);
      el.removeEventListener("keydown", onKey);
      el.removeEventListener("pointerdown", onDown);
      window.removeEventListener("pointerup", onUp);
      observer.disconnect();
    };
  }, [pin, unpin]);

  useLayoutEffect(() => {
    if (messageCount > seenCountRef.current && !pinnedRef.current) setShowJumpToLatest(true);
    seenCountRef.current = messageCount;
  }, [messageCount]);

  return { viewportRef, contentRef, showJumpToLatest, scrollToBottom, unpin };
}
