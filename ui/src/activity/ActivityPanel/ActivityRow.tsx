import { useRef } from "react";
import { AreaChart, Area, Tooltip, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { formatTokens } from "@/shared/formatTokens";
import type { ContextDataPoint } from "../types";
import styles from "./ActivityPanel.module.css";

function CustomTooltip({ active, payload }: { active?: boolean; payload?: Array<{ value: number; payload: ContextDataPoint }> }) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className={styles.chartTooltip}>
      <span>Turn {point.index}</span>
      <span className={styles.chartTooltipValue}>{formatTokens(point.totalContext)} tokens</span>
    </div>
  );
}

export function ContextChart({ data, onClickPoint }: { data: ContextDataPoint[]; onClickPoint: (messageId: string) => void }) {
  const activePointRef = useRef<ContextDataPoint | null>(null);

  if (data.length < 2) return null;

  const handleMouseMove = (state: unknown) => {
    const s = state as { activePayload?: Array<{ payload: ContextDataPoint }> } | null;
    activePointRef.current = s?.activePayload?.[0]?.payload ?? null;
  };

  const handleMouseLeave = () => {
    activePointRef.current = null;
  };

  const handleClick = () => {
    if (activePointRef.current) {
      onClickPoint(activePointRef.current.messageId);
    }
  };

  return (
    <div className={styles.chartContainer}>
      <div className={styles.chartLabel}>Context size</div>
      <ResponsiveContainer width="100%" height={80}>
        <AreaChart
          data={data}
          margin={{ top: 4, right: 4, bottom: 0, left: 4 }}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
          onClick={handleClick}
          style={{ cursor: "pointer" }}
        >
          <defs>
            <linearGradient id="contextGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#6366f1" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#6366f1" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <XAxis dataKey="index" hide />
          <YAxis hide domain={[0, "auto"]} />
          <Tooltip
            content={<CustomTooltip />}
            cursor={{ stroke: "#6366f1", strokeOpacity: 0.3 }}
          />
          <Area
            type="monotone"
            dataKey="totalContext"
            stroke="#6366f1"
            strokeWidth={1.5}
            fill="url(#contextGradient)"
            dot={false}
            activeDot={{ r: 4, fill: "#818cf8", stroke: "#6366f1", strokeWidth: 1, cursor: "pointer" }}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
