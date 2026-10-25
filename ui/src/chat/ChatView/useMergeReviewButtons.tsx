import { useMemo } from "react";
import { FileDiffIcon } from "lucide-react";
import { useAppDispatch } from "@/store";
import { openReview } from "@/store/reviewSlice";
import type { ApprovalActionButton } from "@/approvals/ApprovalShared";

export function useMergeReviewButtons(
  sessionId: string,
  pendingToolUseId: string | undefined,
): ApprovalActionButton[] {
  const dispatch = useAppDispatch();
  return useMemo(
    () => [
      {
        key: "review",
        label: "Review changes",
        shortcut: "R",
        icon: <FileDiffIcon />,
        onClick: () => dispatch(openReview({ sessionId, toolUseId: pendingToolUseId })),
        variant: "approve",
      },
    ],
    [dispatch, sessionId, pendingToolUseId],
  );
}
