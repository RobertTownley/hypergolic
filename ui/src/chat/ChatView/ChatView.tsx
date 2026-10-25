import { Text } from "@/shared/components/Text";
import { Spinner } from "@/shared/components/Spinner";
import { ZapIcon } from "lucide-react";
import { ConversationLedger, Inspector, LedgerProvider } from "@/chat/Ledger";
import { ChatInput } from "@/chat/ChatInput";
import { ToolApprovalInput } from "@/tools/ToolApprovalInput";
import { ArtifactReviewInput } from "@/approvals/ArtifactReviewInput";
import { SessionConclusion } from "@/chat/SessionConclusion";
import { ConcludeSessionModal } from "@/sessions/ConcludeSessionModal";
import { ExportSessionModal } from "@/sessions/ExportSessionModal";
import { EmptyState } from "@/shared/components/EmptyState";
import { useChatView } from "./useChatView";
import { useConcludeModals } from "./useConcludeModals";
import { useMergeReviewButtons } from "./useMergeReviewButtons";
import { StreamingSection } from "./StreamingSection";
import { useAppDispatch, useAppSelector } from "@/store";
import { clearReviewState } from "@/store/reviewSlice";
import { useReviewDenial } from "@/review/useReviewDenial";
import type { Annotation } from "@/types/api";
import styles from "./ChatView.module.css";

interface ChatViewProps {
  sessionId: string;
}

export function ChatView({ sessionId }: ChatViewProps) {
  const {
    messageCount,
    loadingMessages,
    streaming,
    error,
    pendingApproval,
    isTruncating,
    isRetrying,
    sessionStatus,
    viewportRef,
    contentRef,
    showJumpToLatest,
    scrollToBottom,
    handleSend,
    sendApprovalResponse,
  } = useChatView(sessionId);

  const session = useAppSelector((s) => s.sessions.entities[sessionId]);
  const dispatch = useAppDispatch();
  const reviewDenial = useReviewDenial(sessionId);
  const respondToApproval = (approved: boolean, reason?: string) => {
    if (!pendingApproval) return;
    const isLand = pendingApproval.toolId === "land";
    void sendApprovalResponse(
      sessionId, pendingApproval.toolUseId, approved,
      approved ? undefined : isLand ? reviewDenial.reason(reason) : reason,
      isLand ? reviewDenial.annotations : undefined,
    );
    if (isLand) dispatch(clearReviewState({ sessionId }));
  };
  const mergeReviewButtons = useMergeReviewButtons(sessionId, pendingApproval?.toolUseId);
  const {
    showConcludeModal,
    concludeError,
    showExportModal,
    closeConcludeModal,
    closeExportModal,
    handleConclude,
  } = useConcludeModals(sessionId, sessionStatus);

  const empty = messageCount === 0 && !streaming;

  return (
    <LedgerProvider viewportRef={viewportRef} live={streaming}>
      <div className={styles.container}>
        <ConversationLedger
          sessionId={sessionId}
          viewportRef={viewportRef}
          contentRef={contentRef}
          showJumpToLatest={showJumpToLatest}
          onJumpToLatest={scrollToBottom}
        >
          {empty && loadingMessages && (
            <EmptyState className={styles.emptyState}>
              <Spinner size="large" />
            </EmptyState>
          )}
          {empty && !loadingMessages && (
            <EmptyState
              icon={<ZapIcon style={{ fontSize: 48, color: "#2a2a3e" }} />}
              text="Start a conversation"
              className={styles.emptyState}
            />
          )}
          <StreamingSection sessionId={sessionId} isTruncating={isTruncating} isRetrying={isRetrying} />
          {error && (
            <div className={styles.errorMessage}>
              <Text type="danger">{error}</Text>
            </div>
          )}
        </ConversationLedger>
        <div className={styles.inputArea}>
          {sessionStatus === "concluded" || sessionStatus === "concluding" ? (
            <SessionConclusion
              conclusionRating={session?.conclusion_rating ?? null}
              conclusionFeedback={session?.conclusion_feedback ?? null}
              concludedAt={session?.concluded_at ?? null}
              concluding={sessionStatus === "concluding"}
            />
          ) : sessionStatus === "interrupted" ? (
            <div className={styles.sessionNotice}>
              This session was concluded due to a user interruption
            </div>
          ) : pendingApproval && pendingApproval.toolId.startsWith("workflow_transition_") ? (
            <ArtifactReviewInput
              approval={pendingApproval}
              onApprove={(annotations: Annotation[]) =>
                sendApprovalResponse(
                  sessionId,
                  pendingApproval.toolUseId,
                  true,
                  undefined,
                  annotations.length > 0 ? annotations : undefined,
                )
              }
              onDeny={(reason?: string, annotations?: Annotation[]) =>
                sendApprovalResponse(sessionId, pendingApproval.toolUseId, false, reason, annotations)
              }
            />
          ) : pendingApproval ? (
            <ToolApprovalInput
              approval={pendingApproval}
              onApprove={() => respondToApproval(true)}
              onDeny={(reason) => respondToApproval(false, reason)}
              leadingButtons={pendingApproval.toolId === "land" ? mergeReviewButtons : undefined}
            />
          ) : (
            <ChatInput sessionId={sessionId} onSend={handleSend} streaming={streaming} />
          )}
        </div>
        <Inspector />
      </div>
      {showConcludeModal && (
        <ConcludeSessionModal
          onClose={closeConcludeModal}
          onConclude={handleConclude}
          sessionId={sessionId}
          errorDetail={concludeError}
        />
      )}
      {showExportModal && <ExportSessionModal sessionId={sessionId} onClose={closeExportModal} />}
    </LedgerProvider>
  );
}
