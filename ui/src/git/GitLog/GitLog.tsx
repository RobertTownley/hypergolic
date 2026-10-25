import { useEffect } from "react";
import { useAppDispatch, useAppSelector } from "@/store";
import { selectActiveSessionId, selectGitLogEntries, selectGitLogLoading } from "@/store/selectors";
import { loadGitLog, loadCommitDetail } from "@/store/workspaceThunks";
import type { GitLogEntry } from "@/types/api";
import { EmptyState } from "@/shared/components/EmptyState";
import { PanelBody } from "@/shared/components/Panel";
import { Spinner } from "@/shared/components/Spinner";
import styles from "./GitLog.module.css";

function formatRelativeDate(isoDate: string): string {
  const date = new Date(isoDate);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60_000);
  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 30) return `${diffDays}d ago`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function LogEntry({ entry, isFirst, onClick }: { entry: GitLogEntry; isFirst: boolean; onClick: () => void }) {
  const refs = entry.refs
    .split(",")
    .map((r) => r.trim())
    .filter(Boolean);

  return (
    <div className={styles.entry} onClick={onClick}>
      <div className={styles.graph}>
        <div className={`${styles.dot} ${isFirst ? styles.dotHead : ""}`} />
      </div>
      <div className={styles.entryBody}>
        <div className={styles.entryTop}>
          <span className={styles.hash}>{entry.short_hash}</span>
          <span className={styles.message} title={entry.message}>
            {entry.message}
          </span>
          {refs.map((ref) => (
            <span key={ref} className={styles.refTag}>
              {ref}
            </span>
          ))}
        </div>
        <div className={styles.entryMeta}>
          <span className={styles.author}>{entry.author}</span>
          <span className={styles.date}>{formatRelativeDate(entry.date)}</span>
        </div>
      </div>
    </div>
  );
}

export function GitLogList() {
  const dispatch = useAppDispatch();
  const logEntries = useAppSelector(selectGitLogEntries);
  const logLoading = useAppSelector(selectGitLogLoading);
  const activeSessionId = useAppSelector(selectActiveSessionId);

  useEffect(() => {
    if (!activeSessionId) return;
    if (logEntries.length === 0) {
      dispatch(loadGitLog({ sessionId: activeSessionId, count: 50 }));
    }
  }, [dispatch, logEntries.length, activeSessionId]);

  return (
    <PanelBody scrollable className={styles.entries}>
      {logLoading && logEntries.length === 0 ? (
        <Spinner centered />
      ) : logEntries.length === 0 ? (
        <EmptyState text="No commits yet" />
      ) : (
        logEntries.map((entry, i) => (
          <LogEntry
            key={entry.hash}
            entry={entry}
            isFirst={i === 0}
            onClick={() => {
              if (activeSessionId) dispatch(loadCommitDetail({ sessionId: activeSessionId, hash: entry.hash }));
            }}
          />
        ))
      )}
    </PanelBody>
  );
}
