import { useCallback, useMemo, useState } from "react";
import type { PendingApproval } from "@/store/messagesSlice";

export type PendingKey = "y" | "n" | "d" | "c" | null;
type ViewMode = "rendered" | "raw";

interface PendingKeyActions {
  y: () => void;
  n: () => void;
  c?: () => void;
}

interface Params {
  approval: PendingApproval;
  actions: PendingKeyActions;
  intercept?: (e: React.KeyboardEvent) => boolean;
}

export function usePendingKeyShortcuts({ approval, actions, intercept }: Params) {
  const hasRenderedView = !!approval.approvalView && approval.approvalView.blocks.length > 0;
  const showRawJson = approval.approvalView?.show_raw_json ?? true;
  const [viewMode, setViewMode] = useState<ViewMode>(hasRenderedView ? "rendered" : "raw");
  const [pendingKey, setPendingKey] = useState<PendingKey>(null);
  const [showDenyInput, setShowDenyInput] = useState(false);

  const rawJson = useMemo(() => JSON.stringify(approval.toolInput, null, 2), [approval.toolInput]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      if (e.key === "Escape") {
        e.preventDefault();
        setPendingKey(null);
        return;
      }

      if (e.key === "Enter") {
        const run = pendingKey === "d" ? () => setShowDenyInput(true) : pendingKey && actions[pendingKey];
        if (run) {
          e.preventDefault();
          setPendingKey(null);
          run();
        }
        return;
      }

      if (intercept?.(e)) {
        e.preventDefault();
        setPendingKey(null);
        return;
      }

      const key = e.key.toLowerCase();
      if (key === "y" || key === "n" || key === "d" || (key === "c" && actions.c)) {
        e.preventDefault();
        setPendingKey(key);
      } else if (hasRenderedView && showRawJson && key === "j") {
        e.preventDefault();
        setPendingKey(null);
        setViewMode((m) => (m === "rendered" ? "raw" : "rendered"));
      } else {
        setPendingKey(null);
      }
    },
    [pendingKey, actions, intercept, hasRenderedView, showRawJson],
  );

  return {
    viewMode,
    setViewMode,
    hasRenderedView,
    showRawJson,
    rawJson,
    pendingKey,
    showDenyInput,
    setShowDenyInput,
    handleKeyDown,
  };
}
