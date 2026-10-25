import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import type { TimeseriesPoint } from "@/api/analytics";
import { Card } from "@/shared/components/Card";
import { formatTokens } from "@/shared/formatTokens";
import styles from "./AnalyticsPanel.module.css";

function TokensTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value: number; name: string; color: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "#1a1a2e", border: "1px solid #2a2a3e", borderRadius: 6, padding: "8px 12px", fontSize: 11 }}>
      <div style={{ color: "#94a3b8", marginBottom: 4 }}>{label}</div>
      {payload.map((p) => (
        <div key={p.name} style={{ color: p.color, display: "flex", justifyContent: "space-between", gap: 12 }}>
          <span>{p.name}</span>
          <span style={{ fontWeight: 600 }}>{formatTokens(p.value)}</span>
        </div>
      ))}
    </div>
  );
}

export function TokensChart({ data }: { data: TimeseriesPoint[] }) {
  return (
    <Card>
      <div className={styles.chartTitle}>Token Usage</div>
      <div className={styles.chartContainer}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e1e30" />
            <XAxis dataKey="period" tick={{ fill: "#3a3a4e", fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: "#3a3a4e", fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={formatTokens} />
            <Tooltip content={<TokensTooltip />} />
            <Bar dataKey="input_tokens" name="Input" stackId="a" fill="#6366f1" isAnimationActive={false} />
            <Bar dataKey="output_tokens" name="Output" stackId="a" fill="#818cf8" isAnimationActive={false} />
            <Bar dataKey="cache_write_tokens" name="Cache Write" stackId="a" fill="#a5b4fc" isAnimationActive={false} />
            <Bar dataKey="cache_read_tokens" name="Cache Read" stackId="a" fill="#c7d2fe" isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
