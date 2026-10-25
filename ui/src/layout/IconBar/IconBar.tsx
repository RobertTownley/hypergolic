import { Tooltip } from "@/shared/components/Tooltip";
import { BookIcon, ChartColumnIcon, FolderIcon, GitBranchIcon, LayoutGridIcon, MessageSquareIcon, SquareKanbanIcon, WrenchIcon } from "lucide-react";
import { useAppDispatch, useAppSelector } from "@/store";
import { selectActiveSessionId } from "@/store/selectors";
import { useCompactLayout } from "@/hooks/useCompactLayout";
import { setLeftTab, setLeftPanelCollapsed, type LeftTab } from "@/store/uiSlice";
import { useIconBar } from "./useIconBar";
import styles from "./IconBar.module.css";

const logoUrl = "/logo.webp";

interface NavButton {
  tab: LeftTab;
  label: string;
  shortcut: string;
  icon: React.ReactNode;
  sessionRequired?: boolean;
}

const NAV_BUTTONS: NavButton[] = [
  { tab: "git",       label: "Source Control",  shortcut: "\u2318\u0031", icon: <GitBranchIcon />, sessionRequired: true },
  { tab: "files",     label: "File Explorer",   shortcut: "\u2318\u0032", icon: <FolderIcon />,   sessionRequired: true },
  { tab: "projects",  label: "Projects",        shortcut: "\u2318\u0033", icon: <SquareKanbanIcon /> },
  { tab: "harness",   label: "Harness",         shortcut: "\u2318\u0034", icon: <WrenchIcon /> },
  { tab: "help",      label: "Help",            shortcut: "\u2318\u0035", icon: <BookIcon />,    sessionRequired: true },
  { tab: "analytics", label: "Analytics",       shortcut: "\u2318\u0037", icon: <ChartColumnIcon /> },
];

export function IconBar() {
  const dispatch = useAppDispatch();
  const activeTab = useAppSelector((s) => s.ui.leftTab);
  const leftPanelCollapsed = useAppSelector((s) => s.ui.leftPanelCollapsed);
  const activeSessionId = useAppSelector(selectActiveSessionId);
  const compact = useCompactLayout();

  const { setTab, handleFocusToggle, isFocusActive } = useIconBar({
    dispatch, activeTab, leftPanelCollapsed, compact,
  });

  const hasSession = activeSessionId !== null;

  return (
    <div className={styles.container}>
      <div className={styles.logoWrapper}>
        <img src={logoUrl} alt="Hypergolic" className={styles.logo} />
      </div>

      {compact && (
        <Tooltip title="Sessions" placement="right">
          <button
            className={`${styles.tabBtn} ${activeTab === "sessions" ? styles.tabBtnActive : ""}`}
            onClick={() => setTab("sessions")}
            data-tab="sessions"
          >
            <LayoutGridIcon />
          </button>
        </Tooltip>
      )}

      {NAV_BUTTONS.map(({ tab, label, shortcut, icon, sessionRequired }) => {
        if (sessionRequired && !hasSession) return null;
        return (
          <Tooltip key={tab} title={`${label} (${shortcut})`} placement="right">
            <button
              className={`${styles.tabBtn} ${activeTab === tab ? styles.tabBtnActive : ""}`}
              onClick={() => {
                if (tab === "harness") {
                  dispatch(setLeftPanelCollapsed(false));
                  dispatch(setLeftTab("harness"));
                } else {
                  setTab(tab);
                }
              }}
              data-tab={tab}
            >
              {icon}
            </button>
          </Tooltip>
        );
      })}

      <div className={styles.spacer} />

      <Tooltip title={`Focus Mode (\u2318\u0030)`} placement="right">
        <button
          className={`${styles.tabBtn} ${isFocusActive ? styles.tabBtnActive : ""}`}
          onClick={handleFocusToggle}
          data-tab="focus"
        >
          <MessageSquareIcon />
        </button>
      </Tooltip>
    </div>
  );
}
