import type { PerformanceCards } from "@/api/analytics";
import { Card } from "@/shared/components/Card";
import { formatBytes, formatCores, formatSeconds, formatShare } from "./format";
import styles from "../AnalyticsPanel.module.css";

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card>
      <div className={styles.summaryLabel}>{label}</div>
      <div className={styles.summaryValue}>{value}</div>
      {sub && <div className={styles.summarySub}>{sub}</div>}
    </Card>
  );
}

export function PerfCards({ data }: { data: PerformanceCards }) {
  return (
    <div className={styles.summaryGrid}>
      <Stat label="Sandboxes" value={String(data.sandboxes)} sub={`idle: ${data.idle_sandboxes}`} />
      <Stat label="Sandbox CPU now" value={formatCores(data.sandbox_cores)}
        sub={`idle sessions: ${formatShare(data.idle_cpu_share)} of window`} />
      <Stat label="Sandbox memory" value={formatBytes(data.sandbox_memory_bytes)} />
      <Stat label="CPU throttled" value={formatCores(data.throttled_cores)} sub="held back by limits" />
      <Stat label="Harness" value={formatCores(data.harness_cores)}
        sub={`RSS: ${formatBytes(data.harness_rss_bytes)}`} />
      <Stat label="Event-loop lag p95" value={formatSeconds(data.loop_lag_p95_s)} />
    </div>
  );
}
