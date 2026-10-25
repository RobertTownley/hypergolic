import { useRef, useState, useEffect } from "react";
import { useAppSelector } from "@/store";
import { selectActiveSessionId, selectSelectedDiff, selectDiffLoading } from "@/store/selectors";
import { useAttachSelection } from "@/hooks/useAttachSelection";
import { LeftSidebar } from "@/layout/LeftSidebar";
import { DiffViewer } from "@/files/DiffViewer";
import { GitWorkspaceView } from "@/git/GitWorkspaceView";
import { FileViewer } from "@/files/FileViewer";
import { ProjectsPanel } from "@/projects/ProjectsPanel";
import { AnalyticsPanel } from "@/analytics";
import { DocsViewer } from "@/docs/DocsViewer";
import { ChatView } from "@/chat/ChatView";
import { RightSidebar } from "@/layout/RightSidebar";
import { HarnessExplorer } from "@/harness/HarnessExplorer";
import { HarnessFileViewer } from "@/harness/HarnessFileViewer";
import styles from "./LeftWorkspace.module.css";

function GitMainContent() {
  const selectedDiff = useAppSelector(selectSelectedDiff);
  const diffLoading = useAppSelector(selectDiffLoading);
  const hasDiff = selectedDiff !== null || diffLoading;
  const handleAttachSelection = useAttachSelection();
  return hasDiff ? <DiffViewer onAttachSelection={handleAttachSelection} /> : <GitWorkspaceView />;
}

function FilesMainContent() {
  const handleAttachSelection = useAttachSelection();
  return <FileViewer onAttachSelection={handleAttachSelection} />;
}

function CompactChatContent() {
  const activeSessionId = useAppSelector((s) => s.sessions.activeSessionId);
  if (!activeSessionId) return null;
  return <ChatView sessionId={activeSessionId} />;
}

function FullWidthContent({ leftTab }: { leftTab: string }) {
  if (leftTab === "chat") return <CompactChatContent />;
  if (leftTab === "sessions") return <RightSidebar />;
  if (leftTab === "projects") return <ProjectsPanel />;
  if (leftTab === "analytics") return <AnalyticsPanel />;
  return null;
}

function MainContent({ leftTab, hasSession }: { leftTab: string; hasSession: boolean }) {
  if (!hasSession && (leftTab === "git" || leftTab === "files" || leftTab === "help")) {
    return null;
  }
  switch (leftTab) {
    case "git":
      return <GitMainContent />;
    case "files":
      return <FilesMainContent />;
    case "help":
      return <DocsViewer />;
    default:
      return null;
  }
}

function HarnessContent({ stacked }: { stacked: boolean }) {
  return (
    <>
      <div className={stacked ? styles.sidebarStacked : styles.sidebar}>
        <HarnessExplorer />
      </div>
      <div className={styles.mainContent}>
        <HarnessFileViewer />
      </div>
    </>
  );
}

const FULL_WIDTH_TABS = new Set(["chat", "sessions", "projects", "analytics"]);

/** Stack vertically when the container is narrower than this */
const STACK_THRESHOLD = 900;

function useStackedLayout() {
  const ref = useRef<HTMLDivElement>(null);
  const [stacked, setStacked] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setStacked(entry.contentRect.width < STACK_THRESHOLD);
      }
    });

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return { ref, stacked };
}

export function LeftWorkspace() {
  const leftTab = useAppSelector((s) => s.ui.leftTab);
  const activeSessionId = useAppSelector(selectActiveSessionId);
  const { ref, stacked } = useStackedLayout();
  const hasSession = activeSessionId !== null;

  if (leftTab === "harness") {
    return (
      <div ref={ref} className={stacked ? `${styles.container} ${styles.stacked}` : styles.container}>
        <HarnessContent stacked={stacked} />
      </div>
    );
  }

  if (FULL_WIDTH_TABS.has(leftTab)) {
    return (
      <div ref={ref} className={styles.container}>
        <div className={styles.mainContent}>
          <FullWidthContent leftTab={leftTab} />
        </div>
      </div>
    );
  }

  const containerClass = stacked
    ? `${styles.container} ${styles.stacked}`
    : styles.container;

  return (
    <div ref={ref} className={containerClass}>
      <div className={stacked ? styles.sidebarStacked : styles.sidebar}>
        <LeftSidebar />
      </div>
      <div className={styles.mainContent}>
        <MainContent leftTab={leftTab} hasSession={hasSession} />
      </div>
    </div>
  );
}
