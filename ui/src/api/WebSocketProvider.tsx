import { createContext, use, useRef, useEffect, useCallback, type ReactNode } from "react";
import { ChatWebSocket } from "./websocket";
import { handleWsEvent } from "./wsEventHandler";
import { useAppDispatch } from "@/store";
import { clearPendingApproval } from "@/store/messagesSlice";
import type { ModelTier, ContentBlock, Annotation } from "@/types/api";

interface WebSocketContextValue {
  send: (message: string, sessionId: string, modelTier: ModelTier, contentBlocks?: ContentBlock[], workflowId?: string) => Promise<void>;
  sendApprovalResponse: (sessionId: string, toolUseId: string, approved: boolean, denialReason?: string, annotations?: Annotation[]) => Promise<void>;
  sendRaw: (payload: Record<string, unknown>) => Promise<void>;
}

const WebSocketContext = createContext<WebSocketContextValue | null>(null);

export function WebSocketProvider({ children }: { children: ReactNode }) {
  const dispatch = useAppDispatch();
  const wsRef = useRef<ChatWebSocket | null>(null);

  const onEvent = useCallback(
    (event: Parameters<typeof handleWsEvent>[1]) => handleWsEvent(dispatch, event),
    [dispatch],
  );

  useEffect(() => {
    const ws = new ChatWebSocket(onEvent);
    wsRef.current = ws;
    ws.open(); // the server resumes interrupted sessions on first connect
    return () => {
      ws.disconnect();
      wsRef.current = null;
    };
  }, [onEvent]);

  const send = useCallback(
    async (message: string, sessionId: string, modelTier: ModelTier, contentBlocks?: ContentBlock[], workflowId?: string) => {
      const ws = wsRef.current;
      if (!ws) throw new Error("WebSocket not initialized");
      await ws.send(message, sessionId, modelTier, contentBlocks, workflowId);
    },
    [],
  );

  const sendApprovalResponse = useCallback(
    async (sessionId: string, toolUseId: string, approved: boolean, denialReason?: string, annotations?: Annotation[]) => {
      const ws = wsRef.current;
      if (!ws) throw new Error("WebSocket not initialized");
      const payload: Record<string, unknown> = {
        type: "tool_approval_response",
        tool_use_id: toolUseId,
        approved,
        denial_reason: denialReason ?? null,
      };
      if (annotations && annotations.length > 0) {
        payload.annotations = annotations.map((a) => ({
          highlighted_text: a.highlighted_text,
          comment: a.comment,
        }));
      }
      await ws.sendRaw(payload);
      dispatch(clearPendingApproval({ sessionId, toolUseId }));
    },
    [dispatch],
  );

  const sendRaw = useCallback(
    async (payload: Record<string, unknown>) => {
      const ws = wsRef.current;
      if (!ws) throw new Error("WebSocket not initialized");
      await ws.sendRaw(payload);
    },
    [],
  );

  return (
    <WebSocketContext.Provider value={{ send, sendApprovalResponse, sendRaw }}>
      {children}
    </WebSocketContext.Provider>
  );
}

export function useWebSocket(): WebSocketContextValue {
  const ctx = use(WebSocketContext);
  if (!ctx) throw new Error("useWebSocket must be used within WebSocketProvider");
  return ctx;
}
