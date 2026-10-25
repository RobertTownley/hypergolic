import { Text } from "@/shared/components/Text";
import { Spinner } from "@/shared/components/Spinner";
import { RefreshCwIcon, ScissorsIcon } from "lucide-react";
import styles from "./ChatView.module.css";

export type StreamingIndicatorMode = "thinking" | "truncating" | "retrying";

const MODES = {
  thinking: {
    icon: <Spinner size="small" />,
    color: "#64748b",
    text: "Thinking\u2026",
    className: "",
  },
  truncating: {
    icon: <ScissorsIcon style={{ color: "#f97316", fontSize: 14 }} className={styles.truncatingIcon} />,
    color: "#f97316",
    text: "Truncating\u2026",
    className: styles.truncatingIndicator,
  },
  retrying: {
    icon: <RefreshCwIcon className="icon-spin" style={{ color: "#facc15", fontSize: 14 }} />,
    color: "#facc15",
    text: "Model request failed \u2014 retrying\u2026",
    className: styles.retryingIndicator,
  },
} as const;

export function StreamingIndicator({ mode }: { mode: StreamingIndicatorMode }) {
  const m = MODES[mode];
  return (
    <div className={`${styles.streamingIndicator} ${m.className}`}>
      {m.icon}
      <Text style={{ color: m.color, fontSize: 13 }}>{m.text}</Text>
    </div>
  );
}
