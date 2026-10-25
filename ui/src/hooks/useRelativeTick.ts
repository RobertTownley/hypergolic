import { useEffect, useState } from "react";

const TICK_MS = 30_000;

export function useRelativeTick(): number {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), TICK_MS);
    return () => clearInterval(id);
  }, []);
  return tick;
}
