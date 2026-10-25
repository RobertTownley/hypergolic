import { useEffect, useRef, type Dispatch, type SetStateAction } from "react";
import { unifiedSearch } from "@/api/search";
import type { FinderMode, FinderResult } from "../types";

export function useSearch(
  open: boolean,
  query: string,
  mode: FinderMode,
  respectGitignore: boolean,
  includeHidden: boolean,
  projectId: string | undefined,
  setLoading: Dispatch<SetStateAction<boolean>>,
  setResults: Dispatch<SetStateAction<FinderResult[]>>,
  setSelectedIndex: Dispatch<SetStateAction<number>>,
) {
  const searchTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    if (!open) return;
    if (!query.trim()) {
      setResults([]);
      setSelectedIndex(0);
      return;
    }
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await unifiedSearch(query, mode, respectGitignore, includeHidden, projectId);
        const results: FinderResult[] = res.matches.map((m) =>
          m.type === "file"
            ? { type: "file" as const, match: { path: m.path, line: m.line, text: m.text } }
            : { type: "session" as const, match: m },
        );
        setResults(results);
        setSelectedIndex(0);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 150);
    return () => { if (searchTimer.current) clearTimeout(searchTimer.current); };
  }, [query, mode, respectGitignore, includeHidden, open, projectId, setLoading, setResults, setSelectedIndex]);
}
