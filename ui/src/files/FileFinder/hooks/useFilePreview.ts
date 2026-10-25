import { useEffect, useRef, type Dispatch, type SetStateAction } from "react";
import { fetchFileContent } from "@/api/files";
import type { FileContentResponse } from "@/types/api";
import type { FinderResult } from "../types";

export function useFilePreview(
  open: boolean,
  selectedResult: FinderResult | undefined,
  sessionId: string | null,
  setLoading: Dispatch<SetStateAction<boolean>>,
  setError: Dispatch<SetStateAction<string | null>>,
  setPreview: Dispatch<SetStateAction<FileContentResponse | null>>,
) {
  const previewTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const filePath = selectedResult?.type === "file" ? selectedResult.match.path : null;

  useEffect(() => {
    if (!open || !filePath) { setPreview(null); setError(null); return; }
    if (!sessionId) { setPreview(null); setError(null); return; }
    if (previewTimer.current) clearTimeout(previewTimer.current);
    previewTimer.current = setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const content = await fetchFileContent(filePath, { sessionId });
        setPreview(content);
      } catch {
        setError("Unable to load preview");
        setPreview(null);
      } finally {
        setLoading(false);
      }
    }, 80);
    return () => { if (previewTimer.current) clearTimeout(previewTimer.current); };
  }, [open, filePath, sessionId, setLoading, setError, setPreview]);
}
