import { useState, useMemo } from "react";
import { GitBranchIcon } from "lucide-react";
import type { Session } from "@/types/api";
import { SessionCard } from "./SessionCard";
import styles from "./SessionList.module.css";

interface ChildSessionGroupProps {
  sessions: Session[];
  activeSessionId: string | null;
  pulseSessionId: string | null;
  onSelect: (id: string) => void;
  onDelete: (e: React.MouseEvent, id: string) => void;
}

export function ChildSessionGroup({
  sessions,
  activeSessionId,
  pulseSessionId,
  onSelect,
  onDelete,
}: ChildSessionGroupProps) {
  const [expanded, setExpanded] = useState(false);
  const hasActiveChild = useMemo(
    () => sessions.some((c) => c.id === activeSessionId),
    [sessions, activeSessionId],
  );
  const hasActionRequiredChild = useMemo(
    () => sessions.some((c) => c.status === "awaiting_approval" || c.status === "error"),
    [sessions],
  );
  const isOpen = expanded || hasActiveChild || hasActionRequiredChild;

  if (sessions.length === 0) return null;

  return (
    <div className={styles.childGroup}>
      <button
        className={styles.childToggle}
        onClick={() => setExpanded((v) => !v)}
      >
        <GitBranchIcon className={styles.childToggleIcon} />
        <span>
          {isOpen ? "Hide" : "Show"} {sessions.length}{" "}
          {sessions.length === 1 ? "child" : "children"}
        </span>
      </button>
      {isOpen &&
        sessions.map((child) => (
          <div key={child.id} className={styles.childSession}>
            <SessionCard
              session={child}
              isActive={child.id === activeSessionId}
              pulse={child.id === pulseSessionId}
              onSelect={() => onSelect(child.id)}
              onDelete={(e) => onDelete(e, child.id)}
            />
          </div>
        ))}
    </div>
  );
}
