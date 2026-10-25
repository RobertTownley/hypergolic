import { useMemo } from "react";
import { useAppSelector } from "@/store";
import type { ActivityStats, ContextDataPoint } from "../types";
import type { ContentBlock, Message } from "@/types/api";

// Stable fallback: an inline `?? []` returns a fresh identity on every store
// action, re-rendering the panel constantly while a session has no messages.
const NO_MESSAGES: Message[] = [];

export function useActivityPanel() {
  const activeSessionId = useAppSelector((s) => s.sessions.activeSessionId);
  const messages = useAppSelector(
    (s) => (activeSessionId ? s.messages.bySessionId[activeSessionId] : undefined) ?? NO_MESSAGES,
  );

  return useMemo(() => {
    let userMessages = 0;
    let assistantMessages = 0;
    let toolCalls = 0;
    let toolResults = 0;
    let latestInputTokens = 0;
    const contextSeries: ContextDataPoint[] = [];

    for (const msg of messages) {
      if (msg.role === "user") {
        const hasToolResult = msg.content.some((b: ContentBlock) => b.type === "tool_result");
        if (hasToolResult) toolResults++;
        else userMessages++;
      } else if (msg.role === "assistant") {
        assistantMessages++;
        for (const block of msg.content) {
          if (block.type === "tool_call") toolCalls++;
        }
        if (msg.usage) {
          const totalContext =
            (msg.usage.input_tokens ?? 0) +
            (msg.usage.cache_read_input_tokens ?? 0) +
            (msg.usage.cache_creation_input_tokens ?? 0);
          const cacheRead = msg.usage.cache_read_input_tokens ?? 0;
          if (totalContext > 0) {
            latestInputTokens = totalContext;
            contextSeries.push({
              index: contextSeries.length + 1,
              totalContext,
              cacheRead,
              messageId: msg.id,
            });
          }
        }
      }
    }

    const stats: ActivityStats = { userMessages, assistantMessages, toolCalls, toolResults };
    const totalMessages = userMessages + assistantMessages;

    return { stats, totalMessages, latestInputTokens, contextSeries };
  }, [messages]);
}
