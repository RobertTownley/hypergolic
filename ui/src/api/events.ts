import { jsonBody } from "@/api/http";

export type EventAttrs = Record<string, string | number | boolean | null>;

export function track(name: string, attrs: EventAttrs = {}, sessionId: string | null = null): void {
  try {
    const init = { ...jsonBody({ name, attrs, session_id: sessionId }), keepalive: true };
    fetch("/api/telemetry/events", init).catch(() => undefined);
  } catch {
    return;
  }
}
