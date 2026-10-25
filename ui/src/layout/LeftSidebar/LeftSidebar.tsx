import { useAppSelector } from "@/store";
import { selectActiveSessionId } from "@/store/selectors";
import type { LeftTab } from "@/store/uiSlice";
import { FileExplorer } from "@/files/FileExplorer";
import { VersionControl } from "@/git/VersionControl";
import { DocsPanel } from "@/docs/DocsPanel";
import styles from "./LeftSidebar.module.css";

function SidebarContent({ tab }: { tab: LeftTab }) {
  switch (tab) {
    case "git":
      return <VersionControl />;
    case "files":
      return <FileExplorer />;
    case "help":
      return <DocsPanel />;
    case "projects":
    case "harness":
      return null;
  }
}

export function LeftSidebar() {
  const activeTab = useAppSelector((s) => s.ui.leftTab);
  const activeSessionId = useAppSelector(selectActiveSessionId);

  if (activeTab === "chat" || activeTab === "sessions" || activeTab === "projects" || activeTab === "analytics" || activeTab === "harness") return null;

  // Session-scoped tabs render nothing when there's no active session.
  // IconBar hides their buttons too; this guards against stale leftTab values.
  if (activeSessionId === null) return null;

  return (
    <div className={styles.container}>
      <SidebarContent tab={activeTab} />
    </div>
  );
}
