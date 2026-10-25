import {
  AreaChart, Area, XAxis, YAxis, Tooltip, Legend,
  ReferenceLine, ResponsiveContainer,
} from "recharts";
import { formatTokens } from "@/shared/formatTokens";
import { useAppSelector } from "@/store";
import { selectTruncationThreshold } from "@/store/uiSlice";
import type { ContextDataPoint } from "../types";
import styles from "./ActivityModal.module.css";

function formatYAxis(value: number) {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)}k`;
  return value.toString();
}

function niceCeil(v: number) {
  const step = 10 ** Math.floor(Math.log10(Math.max(v, 1))) / 2;
  return Math.ceil(v / step) * step;
}

function ThresholdBreakLabel({ viewBox, threshold }: { viewBox?: { x: number; y: number }; threshold: number }) {
  if (!viewBox) return null;
  const { x, y } = viewBox;
  return (
    <g>
      <path
        d={`M ${x - 6} ${y + 15} l 12 -6 M ${x - 6} ${y + 21} l 12 -6`}
        stroke="#94a3b8"
        strokeWidth={1.2}
        fill="none"
      />
      <text x={x + 10} y={y + 13} fill="#ef4444" fontSize={10} fontWeight={600}>
        {`Truncation Threshold (${formatYAxis(threshold)}) ↑`}
      </text>
    </g>
  );
}

function ChartTooltip({ active, payload }: { active?: boolean; payload?: Array<{ dataKey: string; value: number; color: string; payload: ContextDataPoint }> }) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className={styles.chartTooltip}>
      <div className={styles.chartTooltipTurn}>Turn {point.index}</div>
      <div className={styles.chartTooltipRow}>
        <span className={styles.chartTooltipDot} style={{ background: "#6366f1" }} />
        <span>Context: {formatTokens(point.totalContext)}</span>
      </div>
      <div className={styles.chartTooltipRow}>
        <span className={styles.chartTooltipDot} style={{ background: "#10b981" }} />
        <span>Cache hit: {formatTokens(point.cacheRead)}</span>
      </div>
      <div className={styles.chartTooltipHint}>Click to scroll to message</div>
    </div>
  );
}

export function DetailedChart({ data, onClickPoint }: { data: ContextDataPoint[]; onClickPoint: (messageId: string) => void }) {
  const truncationThreshold = useAppSelector(selectTruncationThreshold);
  const dataMax = Math.max(...data.map((d) => d.totalContext), 0);
  const compressed = dataMax > 0 && truncationThreshold > dataMax * 2;
  const yTop = niceCeil(compressed ? dataMax * 1.25 : Math.max(dataMax, truncationThreshold) * 1.1);
  const yDomain = [0, yTop];

  const handleChartClick = (state: unknown) => {
    const s = state as { activePayload?: Array<{ payload: ContextDataPoint }> } | null;
    if (s?.activePayload?.length) {
      onClickPoint(s.activePayload[0].payload.messageId);
    }
  };

  return (
    <div className={styles.chartSection}>
      <div className={styles.chartTitle}>Context Size Over Time</div>
      <ResponsiveContainer width="100%" height={280}>
        <AreaChart
          data={data}
          margin={{ top: 8, right: 12, bottom: 4, left: 8 }}
          onClick={handleChartClick}
          style={{ cursor: "pointer" }}
        >
          <defs>
            <linearGradient id="modalContextGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#6366f1" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#6366f1" stopOpacity={0.02} />
            </linearGradient>
            <linearGradient id="modalCacheGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#10b981" stopOpacity={0.25} />
              <stop offset="100%" stopColor="#10b981" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="index"
            tick={{ fontSize: 10, fill: "#64748b" }}
            axisLine={{ stroke: "#1e1e30" }}
            tickLine={false}
          />
          <YAxis
            domain={yDomain}
            tickFormatter={formatYAxis}
            tick={{ fontSize: 10, fill: "#64748b" }}
            axisLine={{ stroke: "#1e1e30" }}
            tickLine={false}
            width={44}
          />
          <Tooltip content={<ChartTooltip />} cursor={{ stroke: "#6366f1", strokeOpacity: 0.3 }} />
          <Legend
            verticalAlign="bottom"
            height={28}
            iconType="plainline"
            iconSize={12}
            wrapperStyle={{ fontSize: 11, color: "#94a3b8", paddingTop: 8 }}
          />
          <ReferenceLine
            y={compressed ? yTop : truncationThreshold}
            stroke="#ef4444"
            strokeDasharray="6 4"
            strokeWidth={1}
            label={
              compressed
                ? <ThresholdBreakLabel threshold={truncationThreshold} />
                : {
                    value: "Truncation Threshold",
                    position: "insideTopLeft",
                    fill: "#ef4444",
                    fontSize: 10,
                    fontWeight: 600,
                  }
            }
          />
          <Area
            type="monotone"
            dataKey="totalContext"
            name="Context"
            stroke="#6366f1"
            strokeWidth={1.5}
            fill="url(#modalContextGradient)"
            dot={false}
            activeDot={{ r: 4, fill: "#818cf8", stroke: "#6366f1", strokeWidth: 1.5, cursor: "pointer" }}
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="cacheRead"
            name="Cache Hit"
            stroke="#10b981"
            strokeWidth={1.5}
            fill="url(#modalCacheGradient)"
            dot={false}
            activeDot={{ r: 4, fill: "#34d399", stroke: "#10b981", strokeWidth: 1.5, cursor: "pointer" }}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
