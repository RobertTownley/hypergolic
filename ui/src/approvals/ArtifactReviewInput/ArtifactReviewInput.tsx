import { useCallback, useRef, useMemo } from "react";
import { useAppDispatch, useAppSelector } from "@/store";
import { addAnnotation, removeAnnotation, clearAnnotations } from "@/store/reviewSlice";
import type { PendingApproval } from "@/store/messagesSlice";
import type { Annotation } from "@/types/api";
import { ApprovalView } from "../ApprovalView";
import {
  ApprovalContainer,
  ApprovalHeader,
  ApprovalActions,
  ViewToggle,
  sharedStyles,
} from "../ApprovalShared";
import { useAnnotationLayerWithRef } from "./AnnotationLayer";
import { AnnotationList } from "./AnnotationList";
import styles from "./ArtifactReviewInput.module.css";
import { usePendingKeyShortcuts } from "../usePendingKeyShortcuts";

interface ArtifactReviewInputProps {
  approval: PendingApproval;
  onApprove: (annotations: Annotation[]) => void;
  onDeny: (reason?: string, annotations?: Annotation[]) => void;
}

export function ArtifactReviewInput({ approval, onApprove, onDeny }: ArtifactReviewInputProps) {
  const dispatch = useAppDispatch();
  const sessionId = approval.sessionId;
  // Annotations live in the per-session review slice so they survive
  // session switches (ChatView remounts keyed by sessionId).
  const storedAnnotations = useAppSelector((s) => s.review.bySession[sessionId]?.annotations);
  const annotations = useMemo(() => storedAnnotations ?? [], [storedAnnotations]);
  const markdownPanelRef = useRef<HTMLDivElement>(null);
  const annotationLayer = useAnnotationLayerWithRef({
    contentRef: markdownPanelRef,
    onAdd: (ann) => dispatch(addAnnotation({ sessionId, annotation: ann })),
  });

  const handleApprove = useCallback(() => {
    onApprove(annotations);
    dispatch(clearAnnotations({ sessionId }));
  }, [onApprove, annotations, dispatch, sessionId]);

  const handleDeny = useCallback(
    (reason?: string) => {
      onDeny(reason, annotations.length > 0 ? annotations : undefined);
      dispatch(clearAnnotations({ sessionId }));
    },
    [onDeny, annotations, dispatch, sessionId],
  );

  const actions = useMemo(() => ({ y: handleApprove, n: () => handleDeny() }), [handleApprove, handleDeny]);
  const {
    viewMode,
    setViewMode,
    hasRenderedView,
    showRawJson,
    rawJson,
    pendingKey,
    showDenyInput,
    setShowDenyInput,
    handleKeyDown: handleShortcutKey,
  } = usePendingKeyShortcuts({ approval, actions });

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!annotationLayer.handleKeyDown(e)) handleShortcutKey(e);
    },
    [annotationLayer, handleShortcutKey],
  );

  const showToggle = hasRenderedView && showRawJson;
  const view = approval.approvalView;

  return (
    <ApprovalContainer onKeyDown={handleKeyDown} ariaLabel="Artifact review">
      <ApprovalHeader
        label="Review artifact"
        toolName={approval.toolName}
        rightSlot={showToggle ? <ViewToggle mode={viewMode} onChange={setViewMode} /> : null}
      >
        {annotations.length > 0 && (
          <span className={styles.annotationCount}>
            {annotations.length} annotation{annotations.length !== 1 ? "s" : ""}
          </span>
        )}
      </ApprovalHeader>

      <div className={sharedStyles.body} ref={markdownPanelRef} onMouseUp={annotationLayer.handleMouseUp}>
        <div className={sharedStyles.bodyContent}>
          {viewMode === "rendered" && view ? (
            <ApprovalView view={view} />
          ) : (
            <pre className={sharedStyles.rawJsonPre}>{rawJson}</pre>
          )}
        </div>
      </div>

      <AnnotationList
        annotations={annotations}
        onRemove={(id) => dispatch(removeAnnotation({ sessionId, annotationId: id }))}
      />

      {annotationLayer.toolbar}
      {annotationLayer.input}

      <ApprovalActions
        onApprove={handleApprove}
        onDeny={handleDeny}
        pendingKey={pendingKey}
        showDenyInput={showDenyInput}
        onShowDenyInputChange={setShowDenyInput}
      />
    </ApprovalContainer>
  );
}
