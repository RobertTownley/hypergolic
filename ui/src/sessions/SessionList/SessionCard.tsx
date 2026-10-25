import { Tooltip } from "@/shared/components/Tooltip";
import { Trash2Icon } from "lucide-react";
import { useAppSelector } from "@/store";
import type { Session } from "@/types/api";
import { StatusIndicator } from "@/shared/components/StatusIndicator";
import styles from "./SessionCard.module.css";

function formatRelativeTime(updatedAt: string): string {
  const date = new Date(updatedAt);
  const diffMs = Date.now() - date.getTime();

  if (Number.isNaN(diffMs) || diffMs < 0) return "Updated just now";

  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return "Updated just now";
  if (diffMins < 60) return `Updated ${diffMins}m ago`;
  if (diffHours < 24) return `Updated ${diffHours}h ago`;
  if (diffDays < 7) return `Updated ${diffDays}d ago`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

interface SessionCardProps {
  session: Session;
  isActive: boolean;
  pulse?: boolean;
  hasActiveChildren?: boolean;
  onSelect: () => void;
  onDelete: (e: React.MouseEvent) => void;
}

export function SessionCard({ session, isActive, pulse, hasActiveChildren, onSelect, onDelete }: SessionCardProps) {
  const clientMessageCount = useAppSelector(
    (s) => s.messages.bySessionId[session.id]?.length ?? 0,
  );
  const messageCount = Math.max(session.message_count, clientMessageCount);
  const timeStr = formatRelativeTime(session.updated_at);
  const idSuffix = session.id.slice(-4);
  const fallbackLabel = session.project_name
    ? `${session.project_name} - \u2026${idSuffix}`
    : session.id.slice(0, 8);
  const label = session.description ?? fallbackLabel;

  return (
    <button
      className={`${styles.sessionCard} ${isActive ? styles.sessionCardActive : ""} ${pulse ? styles.sessionCardPulse : ""}`}
      onClick={onSelect}
    >
      <div className={styles.cardIndicator}>
        <StatusIndicator status={session.status} hasActiveChildren={hasActiveChildren} />
      </div>
      <div className={styles.cardContent}>
        <div className={styles.cardTopRow}>
          <span className={styles.cardDescription}>{label}</span>
          {!isActive && (
            <Tooltip title="Delete session">
              <span
                className={styles.cardDeleteBtn}
                onClick={onDelete}
                role="button"
                tabIndex={0}
              >
                <Trash2Icon />
              </span>
            </Tooltip>
          )}
        </div>
        <div className={styles.cardMiddleRow}>
          <span className={styles.cardTime}>{timeStr}</span>
          <span className={styles.cardProjectName}>{session.project_name}</span>
        </div>
        <div className={styles.cardTagsRow}>
          <span className={styles.cardTier}>{session.model_tier}</span>
          <span className={styles.cardMessages}>{messageCount} msgs</span>
          <span className={styles.cardSpacer} />
          <span className={styles.cardRole}>{session.role}</span>
          {session.workflow_state_name && (
            <span className={styles.cardWorkflowLabel}>
              {session.workflow_name ?? session.workflow_id} {"\u203A"} {session.workflow_state_name}
            </span>
          )}
        </div>
      </div>
    </button>
  );
}
