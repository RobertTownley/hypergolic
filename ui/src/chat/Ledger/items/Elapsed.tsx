import { useEffect, useState } from "react";

/** A call this quick needs no clock; one past it earns a visible timer. */
export const ELAPSED_AFTER_MS = 5_000;

export function formatElapsed(ms: number): string {
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${String(s % 60).padStart(2, "0")}s`;
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`;
}

/** Time since `since` (epoch ms), ticking each second, hidden for the first few. */
export function Elapsed({ since }: { since: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const ms = now - since;
  if (ms < ELAPSED_AFTER_MS) return null;
  return <span>{` · ${formatElapsed(ms)}`}</span>;
}
