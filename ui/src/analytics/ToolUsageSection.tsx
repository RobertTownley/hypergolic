import { useMemo } from "react";
import type { ToolCount } from "@/api/analytics";
import { Card } from "@/shared/components/Card";
import styles from "./AnalyticsPanel.module.css";

export function ToolUsageSection({ data }: { data: ToolCount[] }) {
  const maxCount = useMemo(() => Math.max(...data.map((d) => d.count), 1), [data]);

  if (data.length === 0) return null;

  return (
    <Card>
      <div className={styles.chartTitle}>Tool Usage</div>
      {data.slice(0, 20).map((tool) => (
        <div key={tool.tool_name} className={styles.toolRow}>
          <span className={styles.toolName}>{tool.tool_name}</span>
          <div className={styles.toolBar}>
            <div
              className={styles.toolBarFill}
              style={{ width: `${(tool.count / maxCount) * 100}%` }}
            />
          </div>
          <span className={styles.toolCount}>{tool.count}</span>
        </div>
      ))}
    </Card>
  );
}
