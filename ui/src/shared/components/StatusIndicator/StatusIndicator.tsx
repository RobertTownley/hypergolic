import { BanIcon, CircleAlertIcon, CircleCheckIcon, CircleMinusIcon, CircleXIcon, GitBranchIcon, HistoryIcon, LoaderCircleIcon, RefreshCwIcon, ScissorsIcon, WrenchIcon, ZapIcon } from "lucide-react";
import type { SessionStatus } from "@/types/api";
import styles from "./StatusIndicator.module.css";

interface StatusIndicatorProps {
  status: SessionStatus;
  hasActiveChildren?: boolean;
}

export function StatusIndicator({ status, hasActiveChildren }: StatusIndicatorProps) {
  switch (status) {
    case "idle":
      return <CircleMinusIcon className={styles.idle} />;
    case "thinking":
      return <LoaderCircleIcon className={`icon-spin ${styles.thinking} ${styles.pulse}`} />;
    case "truncating":
      return <ScissorsIcon className={`${styles.truncating} ${styles.pulse}`} />;
    case "streaming":
      return <ZapIcon className={`${styles.streaming} ${styles.pulse}`} />;
    case "retrying":
      return <span title="Model request failed; retrying"><RefreshCwIcon className={`icon-spin ${styles.retrying} ${styles.pulse}`} /></span>;
    case "tool_use":
      if (hasActiveChildren) {
        return <GitBranchIcon className={`${styles.toolUse} ${styles.pulse}`} />;
      }
      return <WrenchIcon className={`${styles.toolUse} ${styles.pulse}`} />;
    case "awaiting_approval":
      return <CircleAlertIcon className={`${styles.awaitingApproval} ${styles.pulse}`} />;
    case "error":
      return <CircleXIcon className={styles.error} />;
    case "concluding":
      return <span title="Concluding: distilling learnings"><HistoryIcon className={`${styles.concluding} ${styles.pulse}`} /></span>;
    case "concluded":
      return <CircleCheckIcon className={styles.concluded} />;
    case "interrupted":
      return <BanIcon className={styles.interrupted} />;
  }
}
