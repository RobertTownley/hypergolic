import { useCallback, useState } from "react";
import { GaugeIcon } from "lucide-react";
import { Collapsible } from "@/shared/components/Collapsible";
import { SCROLL_TO_MESSAGE_EVENT } from "../constants";
import { formatTokens } from "@/shared/formatTokens";
import { ActivityModal } from "../ActivityModal";
import { useActivityPanel } from "./useActivityPanel";
import { ContextChart } from "./ActivityRow";
import styles from "./ActivityPanel.module.css";

export function ActivityPanel() {
  const [modalOpen, setModalOpen] = useState(false);
  const { stats, totalMessages, latestInputTokens, contextSeries } = useActivityPanel();

  const handleClickPoint = useCallback((messageId: string) => {
    window.dispatchEvent(new CustomEvent(SCROLL_TO_MESSAGE_EVENT, { detail: { messageId } }));
  }, []);

  return (
    <>
      <Collapsible icon={<GaugeIcon />} title="Activity">
        <div className={styles.statsRow}>
          <div className={styles.stat}>
            <span className={styles.statValue}>{totalMessages}</span>
            <span className={styles.statLabel}>Messages</span>
          </div>
          <div className={styles.stat}>
            <span className={styles.statValue}>
              {latestInputTokens > 0 ? formatTokens(latestInputTokens) : "\u2014"}
            </span>
            <span className={styles.statLabel}>Context</span>
          </div>
          <div className={styles.stat}>
            <span className={styles.statValue}>{stats.toolCalls}</span>
            <span className={styles.statLabel}>Tool Calls</span>
          </div>
        </div>

        <ContextChart data={contextSeries} onClickPoint={handleClickPoint} />

        <button
          className={styles.detailsLink}
          onClick={() => setModalOpen(true)}
        >
          View details
        </button>
      </Collapsible>

      {modalOpen && (
        <ActivityModal stats={stats} contextSeries={contextSeries} onClose={() => setModalOpen(false)} />
      )}
    </>
  );
}
