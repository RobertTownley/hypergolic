import { useEffect, useState } from "react";
import { fetchPerformance, type PerformanceReport } from "@/api/analytics";

const REFRESH_MS = 30_000;

export function usePerformance(minutes: number) {
  const [report, setReport] = useState<PerformanceReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    const load = () =>
      fetchPerformance(minutes)
        .then((r) => {
          if (!live) return;
          setReport(r);
          setError(r.available ? null : r.error);
        })
        .catch((e: Error) => live && setError(e.message));
    void load();
    const timer = setInterval(load, REFRESH_MS);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [minutes]);

  return { report, error };
}
