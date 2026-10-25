import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { SeriesPoint } from "@/api/analytics";
import { Card } from "@/shared/components/Card";
import styles from "../AnalyticsPanel.module.css";

const COLORS = ["#6366f1", "#22c55e", "#f59e0b", "#ec4899", "#06b6d4", "#a855f7", "#ef4444", "#84cc16"];
const AXIS = { fill: "#3a3a4e", fontSize: 10 };

function clock(at: number): string {
  return new Date(at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

interface Props {
  title: string;
  data: SeriesPoint[];
  format: (n: number) => string;
}

export function StackedChart({ title, data, format }: Props) {
  const keys = [...new Set(data.flatMap((p) => Object.keys(p.values)))].sort();
  const rows = data.map((p) => ({ at: p.at, ...p.values }));
  return (
    <Card>
      <div className={styles.chartTitle}>{title}</div>
      <div className={styles.chartContainer}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={rows} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e1e30" />
            <XAxis dataKey="at" tickFormatter={clock} tick={AXIS} axisLine={false} tickLine={false} />
            <YAxis tickFormatter={format} tick={AXIS} axisLine={false} tickLine={false} width={64} />
            <Tooltip labelFormatter={(at) => clock(Number(at))} formatter={(v) => format(Number(v))}
              contentStyle={{ background: "#1a1a2e", border: "1px solid #2a2a3e", fontSize: 11 }} />
            {keys.map((key, i) => (
              <Area key={key} dataKey={key} stackId="1" type="monotone" isAnimationActive={false}
                stroke={COLORS[i % COLORS.length]} fill={COLORS[i % COLORS.length]} fillOpacity={0.25} />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
