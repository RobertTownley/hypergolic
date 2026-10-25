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
import styles from "./AnalyticsPanel.module.css";

function SessionsTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ value: number; name: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "#1a1a2e", border: "1px solid #2a2a3e", borderRadius: 6, padding: "8px 12px", fontSize: 11 }}>
      <div style={{ color: "#94a3b8", marginBottom: 4 }}>{label}</div>
      {payload.map((p) => (
        <div key={p.name} style={{ color: "#e2e8f0" }}>
          <span>{p.name}: </span>
          <span style={{ fontWeight: 600 }}>{p.value}</span>
        </div>
      ))}
    </div>
  );
}

export function SessionsChart({ data }: { data: TimeseriesPoint[] }) {
  return (
    <Card>
      <div className={styles.chartTitle}>Sessions &amp; Messages</div>
      <div className={styles.chartContainer}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e1e30" />
            <XAxis dataKey="period" tick={{ fill: "#3a3a4e", fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: "#3a3a4e", fontSize: 10 }} axisLine={false} tickLine={false} />
            <Tooltip content={<SessionsTooltip />} />
            <Bar dataKey="sessions" name="Sessions" fill="#6366f1" isAnimationActive={false} />
            <Bar dataKey="messages" name="Messages" fill="#4f46e5" opacity={0.5} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
