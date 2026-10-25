import { useEffect, type RefObject } from "react";

export function useResultScroll(
  resultsRef: RefObject<HTMLDivElement | null>,
  selectedIndex: number,
) {
  useEffect(() => {
    const el = resultsRef.current;
    if (!el) return;
    const selected = el.children[selectedIndex] as HTMLElement | undefined;
    selected?.scrollIntoView({ block: "nearest" });
  }, [selectedIndex, resultsRef]);
}
