import { useMemo, useCallback } from "react";
import { WrenchIcon } from "lucide-react";
import { useAppSelector } from "@/store";
import { selectActiveProjectId } from "@/store/selectors";
import type { PendingApproval } from "@/store/messagesSlice";
import type { ApprovalActionButton } from "@/approvals/ApprovalShared";
import { useOpenHarnessSession } from "@/hooks/useOpenHarnessSession";
import { usePendingKeyShortcuts } from "@/approvals/usePendingKeyShortcuts";

interface UseToolApprovalInputParams {
  approval: PendingApproval;
  onApprove: () => void;
  onDeny: (reason?: string) => void;
  leadingButtons?: ApprovalActionButton[];
}

export function useToolApprovalInput({ approval, onApprove, onDeny, leadingButtons }: UseToolApprovalInputParams) {
  const openHarnessSession = useOpenHarnessSession();
  const projectId = useAppSelector(selectActiveProjectId);

  const handleOpenHarness = useCallback(() => {
    const inputSummary = JSON.stringify(approval.toolInput, null, 2);
    const message = [
      `The \`${approval.toolName}\` tool required approval with these parameters:`,
      "```json",
      inputSummary,
      "```",
      projectId ? `Project: \`${projectId}\`` : "",
      "",
      "Help me configure an approval policy for this tool in my harness.",
    ].filter(Boolean).join("\n");
    openHarnessSession(message);
  }, [approval.toolName, approval.toolInput, projectId, openHarnessSession]);

  const extraButtons = useMemo<ApprovalActionButton[]>(
    () => [
      ...(leadingButtons ?? []),
      {
        key: "configure",
        label: "Configure",
        shortcut: "C",
        icon: <WrenchIcon />,
        onClick: handleOpenHarness,
        variant: "secondary",
      },
    ],
    [handleOpenHarness, leadingButtons],
  );

  const actions = useMemo(
    () => ({ y: onApprove, n: () => onDeny(), c: handleOpenHarness }),
    [onApprove, onDeny, handleOpenHarness],
  );

  const intercept = useCallback(
    (e: React.KeyboardEvent) => {
      const leading = leadingButtons?.find((b) => b.shortcut.toLowerCase() === e.key.toLowerCase());
      leading?.onClick();
      return !!leading;
    },
    [leadingButtons],
  );

  const shortcuts = usePendingKeyShortcuts({ approval, actions, intercept });

  return { ...shortcuts, extraButtons };
}
