export interface ActivityStats {
  userMessages: number;
  assistantMessages: number;
  toolCalls: number;
  toolResults: number;
}

export interface ContextDataPoint {
  index: number;
  totalContext: number;
  cacheRead: number;
  messageId: string;
}
