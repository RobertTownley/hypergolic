import { useState, useCallback, useRef } from "react";

export interface LineSelection {
  start: number;
  end: number;
}

export function selectionBounds(sel: LineSelection): { selStart: number; selEnd: number } {
  return {
    selStart: Math.min(sel.start, sel.end),
    selEnd: Math.max(sel.start, sel.end),
  };
}

export function useLineSelection() {
  const [lineSelection, setLineSelection] = useState<LineSelection | null>(null);
  const [selecting, setSelecting] = useState(false);
  const selectingRef = useRef(false);
  const anchorLineRef = useRef<number | null>(null);

  const handleLineMouseDown = useCallback((index: number, shiftKey: boolean) => {
    if (shiftKey && anchorLineRef.current !== null) {
      setLineSelection({ start: anchorLineRef.current, end: index });
      return;
    }
    anchorLineRef.current = index;
    setLineSelection({ start: index, end: index });
    setSelecting(true);
    selectingRef.current = true;

    const handleMouseUp = () => {
      selectingRef.current = false;
      setSelecting(false);
      window.removeEventListener("mouseup", handleMouseUp);
    };
    window.addEventListener("mouseup", handleMouseUp);
  }, []);

  const handleLineMouseEnter = useCallback((index: number) => {
    if (selectingRef.current) {
      setLineSelection((prev) =>
        prev ? { start: prev.start, end: index } : null,
      );
    }
  }, []);

  const clearSelection = useCallback(() => {
    setLineSelection(null);
    anchorLineRef.current = null;
  }, []);

  return {
    lineSelection,
    selecting,
    handleLineMouseDown,
    handleLineMouseEnter,
    clearSelection,
    setLineSelection,
  };
}
