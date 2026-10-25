import { useMemo } from "react";
import { GaugeIcon } from "lucide-react";
import { Modal } from "@/shared/components/Modal";
import type { ActivityStats, ContextDataPoint } from "../types";
import { useActivityModal } from "./useActivityModal";
import { DetailedChart } from "./DetailedChart";
import styles from "./ActivityModal.module.css";

interface ActivityModalProps {
  stats: ActivityStats;
  contextSeries: ContextDataPoint[];
  onClose: () => void;
}

export function ActivityModal({ stats, contextSeries, onClose }: ActivityModalProps) {
  const { handleClickPoint, totalMessages, hasChart } = useActivityModal(stats, contextSeries, onClose);

  const bodyContent = useMemo(() => (
    <div className={hasChart ? styles.bodyColumns : styles.bodySimple}>
      <div className={styles.statGrid}>
        <div className={styles.statItem}>
          <span className={styles.statValue}>{totalMessages}</span>
          <span className={styles.statLabel}>Total Messages</span>
        </div>
        <div className={styles.statItem}>
          <span className={styles.statValue}>{stats.userMessages}</span>
          <span className={styles.statLabel}>User Messages</span>
        </div>
        <div className={styles.statItem}>
          <span className={styles.statValue}>{stats.assistantMessages}</span>
          <span className={styles.statLabel}>Assistant Messages</span>
        </div>
        <div className={styles.statItem}>
          <span className={styles.statValue}>{stats.toolCalls}</span>
          <span className={styles.statLabel}>Tool Calls</span>
        </div>
        <div className={styles.statItem}>
          <span className={styles.statValue}>{stats.toolResults}</span>
          <span className={styles.statLabel}>Tool Results</span>
        </div>
      </div>
      {hasChart && <DetailedChart data={contextSeries} onClickPoint={handleClickPoint} />}
    </div>
  ), [hasChart, totalMessages, stats, contextSeries, handleClickPoint]);

  return (
    <Modal
      onClose={onClose}
      title="Session Activity"
      icon={<GaugeIcon />}
      width={hasChart ? 820 : 380}
    >
      {bodyContent}
    </Modal>
  );
}
