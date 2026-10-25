import type { AnalyticsSummary } from "@/api/analytics";
import { Card } from "@/shared/components/Card";
import { formatCost } from "./formatters";
import { formatTokens } from "@/shared/formatTokens";
import styles from "./AnalyticsPanel.module.css";

export function SummaryCards({ data }: { data: AnalyticsSummary }) {
  return (
    <div className={styles.summaryGrid}>
      <Card>
        <div className={styles.summaryLabel}>Total Cost</div>
        <div className={styles.summaryValue}>{formatCost(data.total_cost)}</div>
      </Card>
      <Card>
        <div className={styles.summaryLabel}>Sessions</div>
        <div className={styles.summaryValue}>{data.total_sessions}</div>
      </Card>
      <Card>
        <div className={styles.summaryLabel}>Messages</div>
        <div className={styles.summaryValue}>{data.total_messages.toLocaleString()}</div>
      </Card>
      <Card>
        <div className={styles.summaryLabel}>Input Tokens</div>
        <div className={styles.summaryValue}>{formatTokens(data.total_input_tokens)}</div>
      </Card>
      <Card>
        <div className={styles.summaryLabel}>Output Tokens</div>
        <div className={styles.summaryValue}>{formatTokens(data.total_output_tokens)}</div>
      </Card>
      <Card>
        <div className={styles.summaryLabel}>Cache Writes</div>
        <div className={styles.summaryValue}>{formatTokens(data.total_cache_write_tokens)}</div>
        <div className={styles.summarySub}>
          reads: {formatTokens(data.total_cache_read_tokens)}
        </div>
      </Card>
    </div>
  );
}
