import { useEffect, type RefObject } from "react";
import { FILE_FINDER_OPEN_EVENT } from "../types";

export function useFinderLifecycle(
  open: boolean,
  setOpen: (v: boolean) => void,
  close: () => void,
  inputRef: RefObject<HTMLInputElement | null>,
) {
  useEffect(() => {
    const handleOpen = () => setOpen(true);
    window.addEventListener(FILE_FINDER_OPEN_EVENT, handleOpen);
    return () => window.removeEventListener(FILE_FINDER_OPEN_EVENT, handleOpen);
  }, [setOpen]);

  useEffect(() => {
    if (!open) return;
    requestAnimationFrame(() => inputRef.current?.focus());

    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        close();
      }
    };
    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
  }, [open, close, inputRef]);
}
