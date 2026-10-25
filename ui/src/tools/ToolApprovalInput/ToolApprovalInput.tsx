import { ApprovalView } from "@/approvals/ApprovalView";
import {
  ApprovalContainer,
  ApprovalHeader,
  ApprovalActions,
  ViewToggle,
  sharedStyles,
} from "@/approvals/ApprovalShared";
import type { PendingApproval } from "@/store/messagesSlice";
import type { ApprovalActionButton } from "@/approvals/ApprovalShared";
import { useToolApprovalInput } from "./useToolApprovalInput";

interface ToolApprovalInputProps {
  approval: PendingApproval;
  onApprove: () => void;
  onDeny: (reason?: string) => void;
  leadingButtons?: ApprovalActionButton[];
}

export function ToolApprovalInput({ approval, onApprove, onDeny, leadingButtons }: ToolApprovalInputProps) {
  const {
    viewMode,
    setViewMode,
    hasRenderedView,
    showRawJson,
    rawJson,
    extraButtons,
    handleKeyDown,
    pendingKey,
    showDenyInput,
    setShowDenyInput,
  } = useToolApprovalInput({ approval, onApprove, onDeny, leadingButtons });

  const showToggle = hasRenderedView && showRawJson;
  const view = approval.approvalView;

  return (
    <ApprovalContainer onKeyDown={handleKeyDown} ariaLabel="Tool approval">
      <ApprovalHeader
        label="Tool requires approval"
        toolName={approval.toolName}
        rightSlot={showToggle ? <ViewToggle mode={viewMode} onChange={setViewMode} /> : null}
      />

      <div className={sharedStyles.body}>
        <div className={sharedStyles.bodyContent}>
          {viewMode === "rendered" && view ? (
            <ApprovalView view={view} />
          ) : (
            <pre className={sharedStyles.rawJsonPre}>{rawJson}</pre>
          )}
        </div>
      </div>

      <ApprovalActions
        onApprove={onApprove}
        onDeny={onDeny}
        extraButtons={extraButtons}
        pendingKey={pendingKey}
        showDenyInput={showDenyInput}
        onShowDenyInputChange={setShowDenyInput}
      />
    </ApprovalContainer>
  );
}
