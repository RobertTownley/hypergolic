import { useEffect } from "react";
import { FaceSlightlySmilingIcon } from "lucide-react";
import { useAppDispatch, useAppSelector } from "@/store";
import {
  selectActiveSessionId,
  selectActiveWorkspace,
  selectChanges,
  selectChangesLoading,
} from "@/store/selectors";
import { loadChanges } from "@/store/workspaceThunks";
import type { DiffMode } from "@/types/api";
import { EmptyState } from "@/shared/components/EmptyState";
import { PanelBody } from "@/shared/components/Panel";
import { Spinner } from "@/shared/components/Spinner";
import { FileCard } from "./FileCard";
import styles from "./GitWorkspaceView.module.css";

// Beyond this many files, start cards collapsed so the panel stays paintable.
const COLLAPSE_THRESHOLD = 15;

export function InlineChanges({ mode }: { mode: DiffMode }) {
  const dispatch = useAppDispatch();
  const sessionId = useAppSelector(selectActiveSessionId);
  const { status } = useAppSelector(selectActiveWorkspace);
  const changes = useAppSelector(selectChanges);
  const loading = useAppSelector(selectChangesLoading);

  // Refetch whenever git status changes so commits/edits stay in sync.
  useEffect(() => {
    if (sessionId) dispatch(loadChanges({ sessionId, mode }));
  }, [dispatch, sessionId, mode, status]);

  if (changes === null) {
    return loading ? <Spinner centered /> : null;
  }

  return (
    <PanelBody scrollable className={styles.changesBody}>
      {changes.length === 0 ? (
        <EmptyState
          icon={<FaceSlightlySmilingIcon />}
          text={mode === "all" ? "No changes vs base branch" : "Working tree clean"}
        />
      ) : (
        changes.map((file) => (
          <FileCard key={file.path} file={file} defaultCollapsed={changes.length > COLLAPSE_THRESHOLD} />
        ))
      )}
    </PanelBody>
  );
}
