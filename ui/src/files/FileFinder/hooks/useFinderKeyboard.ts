import { useCallback, type Dispatch, type SetStateAction } from "react";
import type { FinderMode, FinderResult } from "../types";

export function useFinderKeyboard(
  results: FinderResult[],
  selectedIndex: number,
  setSelectedIndex: Dispatch<SetStateAction<number>>,
  setMode: Dispatch<SetStateAction<FinderMode>>,
  setRespectGitignore: Dispatch<SetStateAction<boolean>>,
  setIncludeHidden: Dispatch<SetStateAction<boolean>>,
  openResult: (result: FinderResult) => void,
  close: () => void,
) {
  return useCallback(
    (e: React.KeyboardEvent) => {
      const isMod = e.metaKey || e.ctrlKey;

      if (e.key === "Escape") { e.preventDefault(); close(); return; }
      if (e.key === "ArrowDown") { e.preventDefault(); setSelectedIndex((i) => Math.min(i + 1, results.length - 1)); return; }
      if (e.key === "ArrowUp") { e.preventDefault(); setSelectedIndex((i) => Math.max(i - 1, 0)); return; }

      if (e.key === "Enter" && results.length > 0) {
        e.preventDefault();
        openResult(results[selectedIndex]);
        return;
      }

      if (isMod) {
        const modeKeys: Record<string, FinderMode> = { f: "files", c: "contents", a: "all", s: "sessions" };
        if (e.key in modeKeys) { e.preventDefault(); setMode(modeKeys[e.key]); return; }
        if (e.key === "g") { e.preventDefault(); setRespectGitignore((v) => !v); return; }
        if (e.key === "h") { e.preventDefault(); setIncludeHidden((v) => !v); return; }
      }
    },
    [results, selectedIndex, openResult, close, setSelectedIndex, setMode, setRespectGitignore, setIncludeHidden],
  );
}
