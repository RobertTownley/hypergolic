import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import type { TimeseriesPoint } from "@/api/analytics";
import { Card } from "@/shared/components/Card";
import { formatCost } from "./formatters";
import styles from "./AnalyticsPanel.module.css";

function CostTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value: number }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "#1a1a2e", border: "1px solid #2a2a3e", borderRadius: 6, padding: "8px 12px", fontSize: 11 }}>
      <div style={{ color: "#94a3b8", marginBottom: 4 }}>{label}</div>
      <div style={{ color: "#e2e8f0", fontWeight: 600 }}>{formatCost(payload[0].value)}</div>
    </div>
  );
}

export function CostChart({ data }: { data: TimeseriesPoint[] }) {
  return (
    <Card>
      <div className={styles.chartTitle}>Cost Over Time</div>
      <div className={styles.chartContainer}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
            <defs>
              <linearGradient id="costGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#6366f1" stopOpacity={0.3} />
                <stop offset="100%" stopColor="#6366f1" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e1e30" />
            <XAxis dataKey="period" tick={{ fill: "#3a3a4e", fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: "#3a3a4e", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${v}`} />
            <Tooltip content={<CostTooltip />} />
            <Area
              type="monotone"
              dataKey="cost"
              stroke="#6366f1"
              strokeWidth={2}
              fill="url(#costGradient)"
              dot={false}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
