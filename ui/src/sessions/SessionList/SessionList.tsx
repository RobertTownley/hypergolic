import { useMemo, useState } from "react";
import { useRelativeTick } from "@/hooks/useRelativeTick";
import { HistoryIcon, PlusIcon } from "lucide-react";
import { NewSessionModal } from "@/sessions/NewSessionModal";
import { SessionCard } from "./SessionCard";
import { ChildSessionGroup } from "./ChildSessionGroup";
import { hasBusyChild, isTerminal } from "./utils";
import { EmptyState } from "@/shared/components/EmptyState";
import { useSessionList } from "./useSessionList";
import styles from "./SessionList.module.css";

export function SessionList() {
  useRelativeTick();
  const {
    ids,
    entities,
    activeSessionId,
    getChildSessions,
    showModal,
    setShowModal,
    pulseSessionId,
    activeProjectId,
    triggerNewSession,
    handleNewSession,
    handleSelectSession,
    handleDeleteSession,
  } = useSessionList();

  const [showTerminal, setShowTerminal] = useState(false);

  const rootIds = useMemo(
    () => ids.filter((id: string) => !entities[id]?.parent_id),
    [ids, entities],
  );

  const activeRootIds = useMemo(
    () => rootIds.filter((id: string) => { const s = entities[id]; return s && !isTerminal(s); }),
    [rootIds, entities],
  );

  const terminalRootIds = useMemo(
    () => rootIds.filter((id: string) => { const s = entities[id]; return s && isTerminal(s); }),
    [rootIds, entities],
  );

  const concludingCount = useMemo(
    () => terminalRootIds.filter((id: string) => entities[id]?.status === "concluding").length,
    [terminalRootIds, entities],
  );

  function renderSession(id: string, index: number, arr: string[]) {
    const session = entities[id];
    if (!session) return null;
    const children = getChildSessions(id);
    return (
      <div key={id}>
        <SessionCard
          session={session}
          isActive={id === activeSessionId}
          pulse={id === pulseSessionId}
          hasActiveChildren={hasBusyChild(children)}
          onSelect={() => handleSelectSession(id)}
          onDelete={(e) => handleDeleteSession(e, id)}
        />
        <ChildSessionGroup
          sessions={children}
          activeSessionId={activeSessionId}
          pulseSessionId={pulseSessionId}
          onSelect={handleSelectSession}
          onDelete={handleDeleteSession}
        />
        {index < arr.length - 1 && <div className={styles.sessionDivider} />}
      </div>
    );
  }

  return (
    <>
      <button
        className={styles.newSessionBtn}
        onClick={triggerNewSession}
        disabled={!activeProjectId}
      >
        <PlusIcon />
        <span>New Session</span>
      </button>

      <div className={styles.divider} />

      <div className={styles.sessionList}>
        {activeRootIds.map((id: string, i: number, arr: string[]) => renderSession(id, i, arr))}

        {ids.length === 0 && (
          <EmptyState text="No sessions yet" />
        )}

        {showTerminal && terminalRootIds.length > 0 && (
          <>
            <div className={styles.sessionDivider} />
            {terminalRootIds.map((id: string, i: number, arr: string[]) => renderSession(id, i, arr))}
          </>
        )}
      </div>

      {terminalRootIds.length > 0 && (
        <div className={styles.terminalToggleWrap}>
          <button
            className={styles.terminalToggle}
            onClick={() => setShowTerminal((v) => !v)}
          >
            <HistoryIcon />
            <span>
              {showTerminal ? "Hide" : "Show"} {terminalRootIds.length - concludingCount} concluded{concludingCount > 0 ? ` (${concludingCount} concluding)` : ""}
            </span>
          </button>
        </div>
      )}

      {showModal && (
        <NewSessionModal
          onClose={() => setShowModal(false)}
          onCreate={handleNewSession}
        />
      )}
    </>
  );
}
