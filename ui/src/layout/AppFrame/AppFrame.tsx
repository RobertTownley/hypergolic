import { IconBar } from "@/layout/IconBar";
import { LeftWorkspace } from "@/layout/LeftWorkspace";
import { CommitDetailModal } from "@/git/CommitDetailModal";
import { FileFinder } from "@/files/FileFinder";
import { RightSidebar } from "@/layout/RightSidebar";
import { ActiveSession } from "@/ActiveSession";
import { useAppFrame } from "./useAppFrame";
import styles from "./AppFrame.module.css";

const RIGHT_SIDEBAR_WIDTH = 280;

export function AppFrame() {
  const { compact, leftPanelCollapsed, rightPanelCollapsed } = useAppFrame();

  return (
    <div className={styles.appContainer}>
      <div className={styles.mainContent}>
        <div className={styles.iconBarContainer}>
          <IconBar />
        </div>
        {!(leftPanelCollapsed && !compact) && <LeftWorkspace />}
        {!compact && (
          <>
            <div className={styles.centerContent}>
              <ActiveSession />
            </div>
            {!rightPanelCollapsed && (
              <aside className={styles.rightSidebar} style={{ width: RIGHT_SIDEBAR_WIDTH }}>
                <RightSidebar />
              </aside>
            )}
          </>
        )}
        <CommitDetailModal />
        <FileFinder />
      </div>
    </div>
  );
}
