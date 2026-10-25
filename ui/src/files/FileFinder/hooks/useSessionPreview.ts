import { useEffect, type Dispatch, type SetStateAction } from "react";
import { fetchMessages } from "@/api/sessions";
import type { Message } from "@/types/api";
import type { FinderResult } from "../types";

export function useSessionPreview(
  open: boolean,
  selectedResult: FinderResult | undefined,
  setLoading: Dispatch<SetStateAction<boolean>>,
  setMessages: Dispatch<SetStateAction<Message[] | null>>,
) {
  const sessionId = selectedResult?.type === "session" ? selectedResult.match.session_id : null;

  useEffect(() => {
    if (!open || sessionId === null) {
      setMessages(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    fetchMessages(sessionId)
      .then((msgs) => {
        if (!cancelled) setMessages(msgs.slice(0, 10));
      })
      .catch(() => {
        if (!cancelled) setMessages(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [open, sessionId, setLoading, setMessages]);
}
