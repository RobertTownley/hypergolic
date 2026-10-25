import type { WsEvent, ModelTier, ContentBlock } from "@/types/api";

type EventHandler = (event: WsEvent) => void;

// A restart is a ~2s outage and the server resumes interrupted sessions on the
// next connection, so the reconnect ladder stays short: a 10s backoff meant a
// resumed turn sat idle long enough for the user to conclude it was dead.
const MAX_RECONNECT_DELAY_MS = 2000;
const INITIAL_RECONNECT_DELAY_MS = 250;

export class ChatWebSocket {
  private ws: WebSocket | null = null;
  private handler: EventHandler;
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private shouldReconnect = true;
  private connectingPromise: Promise<void> | null = null;

  constructor(handler: EventHandler) {
    this.handler = handler;
  }

  connect(): Promise<void> {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return Promise.resolve();
    }

    if (this.connectingPromise) {
      return this.connectingPromise;
    }

    this.connectingPromise = new Promise<void>((resolve, reject) => {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const url = `${protocol}//${window.location.host}/ws`;
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        this.reconnectAttempt = 0;
        this.connectingPromise = null;
        resolve();
      };

      this.ws.onmessage = (event) => {
        const data: WsEvent = JSON.parse(event.data);
        this.handler(data);
      };

      this.ws.onerror = () => {
        this.connectingPromise = null;
        reject(new Error("WebSocket connection failed"));
      };

      this.ws.onclose = () => {
        this.ws = null;
        this.connectingPromise = null;
        this.scheduleReconnect();
      };
    });

    return this.connectingPromise;
  }

  /** Open in the background. A failed attempt is not an error here: onclose
   *  follows onerror and schedules a retry on the reconnect ladder. */
  open(): void {
    this.connect().catch(() => {});
  }

  private scheduleReconnect() {
    if (!this.shouldReconnect) return;
    if (this.reconnectTimer) return;

    const delay = Math.min(
      INITIAL_RECONNECT_DELAY_MS * 2 ** this.reconnectAttempt,
      MAX_RECONNECT_DELAY_MS,
    );
    this.reconnectAttempt++;

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect().catch(() => {});
    }, delay);
  }

  async send(
    message: string,
    sessionId: string | null,
    modelTier: ModelTier = "High",
    contentBlocks?: ContentBlock[],
    workflowId?: string,
  ) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      await this.connect();
    }
    this.ws!.send(
      JSON.stringify({
        type: "chat",
        message,
        model_tier: modelTier,
        session_id: sessionId,
        content_blocks: contentBlocks?.length ? contentBlocks : undefined,
        workflow_id: workflowId ?? undefined,
      }),
    );
  }

  async sendRaw(payload: Record<string, unknown>) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      await this.connect();
    }
    this.ws!.send(JSON.stringify(payload));
  }

  disconnect() {
    this.shouldReconnect = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.connectingPromise = null;
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}
