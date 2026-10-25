import { useCallback, useMemo } from "react";
import { SCROLL_TO_MESSAGE_EVENT } from "../constants";
import type { ActivityStats, ContextDataPoint } from "../types";

export function useActivityModal(
  stats: ActivityStats,
  contextSeries: ContextDataPoint[],
  onClose: () => void,
) {
  const handleClickPoint = useCallback((messageId: string) => {
    onClose();
    requestAnimationFrame(() => {
      window.dispatchEvent(new CustomEvent(SCROLL_TO_MESSAGE_EVENT, { detail: { messageId } }));
    });
  }, [onClose]);

  const totalMessages = stats.userMessages + stats.assistantMessages;
  const hasChart = contextSeries.length >= 2;

  return useMemo(() => ({
    handleClickPoint,
    totalMessages,
    hasChart,
  }), [handleClickPoint, totalMessages, hasChart]);
}
