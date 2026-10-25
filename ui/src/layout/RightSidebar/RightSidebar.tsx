import { Text } from "@/shared/components/Text";
import { useCallback, useEffect, useState } from "react";
import { DropdownMenu, type MenuItem } from "@/shared/components/DropdownMenu";
import { CircleCheckIcon, CopyIcon, DownloadIcon, EllipsisVerticalIcon, GitBranchIcon } from "lucide-react";
import { useAppDispatch, useAppSelector } from "@/store";
import { selectActiveProject } from "@/store/selectors";
import { loadSessionContext } from "@/store/sessionsSlice";
import { ActivityPanel } from "@/activity/ActivityPanel";
import { MCPSection } from "@/config/MCPSection";
import { SessionList } from "@/sessions/SessionList";
import { SkillsButton, ToolsButton, SystemPromptButton, TokenCostSummary } from "@/sessions/SessionInfoBar";
import { Badge } from "@/shared/components/Badge";
import { CONCLUDE_SESSION_EVENT, EXPORT_SESSION_EVENT } from "@/hooks/useKeyboardShortcuts";
import styles from "./RightSidebar.module.css";

function SessionIdCopyRow({ sessionId }: { sessionId: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(sessionId).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [sessionId]);

  const shortId = sessionId.slice(0, 13) + "\u2026";

  const menuItems: MenuItem[] = [
    {
      key: "copy",
      icon: <CopyIcon />,
      label: copied ? "Copied!" : "Copy Session ID",
      onClick: handleCopy,
    },
    {
      key: "export",
      icon: <DownloadIcon />,
      label: "Export Session",
      onClick: () => window.dispatchEvent(new Event(EXPORT_SESSION_EVENT)),
    },
    {
      type: "divider",
    },
    {
      key: "conclude",
      icon: <CircleCheckIcon />,
      label: "Conclude Session",
      onClick: () => window.dispatchEvent(new Event(CONCLUDE_SESSION_EVENT)),
    },
  ];

  return (
    <div className={styles.sessionIdRow}>
      <span className={styles.sessionTagline}>
        Session: {shortId}
      </span>
      <DropdownMenu items={menuItems} align="end">
        <button className={styles.copyBtn} aria-label="Session actions">
          <EllipsisVerticalIcon />
        </button>
      </DropdownMenu>
    </div>
  );
}

function ProjectLabel() {
  const project = useAppSelector(selectActiveProject);
  if (!project) return null;
  return (
    <div className={styles.projectLabel}>
      <Text
        className={styles.projectLabelText}
        ellipsis
      >
        {project.name}
      </Text>
    </div>
  );
}

export function RightSidebar() {
  const dispatch = useAppDispatch();
  const activeSessionId = useAppSelector((s) => s.sessions.activeSessionId);
  const activeSession = useAppSelector((s) =>
    activeSessionId ? s.sessions.entities[activeSessionId] : null,
  );

  useEffect(() => {
    if (activeSessionId) {
      dispatch(loadSessionContext(activeSessionId));
    }
  }, [activeSessionId, dispatch]);

  return (
    <div className={styles.sidebar}>
      <ProjectLabel />
      {activeSessionId && (
        <div className={styles.sessionHeader}>
          <SessionIdCopyRow sessionId={activeSessionId} />
          {activeSession && activeSession.role !== "generalist" && (
            <div className={styles.roleTag}>
              Role: {activeSession.role}
            </div>
          )}
          {activeSession?.workflow_state_name && (
            <Badge variant="primary" className={styles.workflowBadge}>
              <GitBranchIcon /> {activeSession.workflow_name ?? activeSession.workflow_id} {"\u203A"} {activeSession.workflow_state_name}
            </Badge>
          )}
        </div>
      )}
      <SessionList />
      <ActivityPanel />
      <MCPSection />
      <SkillsButton />
      <ToolsButton />
      <SystemPromptButton />
      <TokenCostSummary />
    </div>
  );
}
