import { useState, useEffect, useRef } from "react";
import { MarkdownContent } from "./MarkdownContent";

const THROTTLE_MS = 80;

/** Markdown that re-renders at most every THROTTLE_MS during streaming. */
export function ThrottledMarkdown({ text }: { text: string }) {
  const [rendered, setRendered] = useState(text);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latestRef = useRef(text);

  // Throttle: schedule one pending flush; ignore further `text` changes until
  // it fires. Cleanup must NOT clear on every `text` change or the timer would
  // be reset every keystroke and never fire. Unmount cleanup lives below.
  useEffect(() => {
    latestRef.current = text;
    if (timerRef.current !== null) return;
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      setRendered(latestRef.current);
    }, THROTTLE_MS);
  }, [text]);

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, []);

  return <MarkdownContent text={rendered} />;
}
