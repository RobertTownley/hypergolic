import type { Session, SessionStatus } from "@/types/api";

const BUSY_STATUSES: Set<SessionStatus> = new Set([
  "thinking",
  "streaming",
  "retrying",
  "tool_use",
  "truncating",
  "awaiting_approval",
]);

const TERMINAL_STATUSES: Set<SessionStatus> = new Set([
  "concluding",
  "concluded",
  "interrupted",
]);

export function hasBusyChild(children: Session[]): boolean {
  return children.some((c) => BUSY_STATUSES.has(c.status));
}

export function isTerminal(session: Session): boolean {
  return TERMINAL_STATUSES.has(session.status);
}
