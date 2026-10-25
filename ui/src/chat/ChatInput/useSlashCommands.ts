import { useCallback } from "react";
import { useAppDispatch } from "@/store";
import { setActiveSession, upsertSession } from "@/store/sessionsSlice";
import { addUserMessage, loadMessages, setSessionError, setSessionStreaming } from "@/store/messagesSlice";
import { useWebSocket } from "@/api/WebSocketProvider";
import { forkSession } from "@/api/sessions";
import type { ContentBlock } from "@/types/api";
import type { SlashCommand } from "./slashCommands";

/**
 * Executes a parsed slash command. Returns once the command has fully taken
 * effect so the caller can clear the draft only on success.
 */
export function useSlashCommands(sessionId: string) {
  const dispatch = useAppDispatch();
  const { send } = useWebSocket();

  return useCallback(
    async (command: SlashCommand, args: string, contentBlocks?: ContentBlock[]) => {
      if (command.name === "fork" || command.name === "fork-with-workspace") {
        const forked = await forkSession(sessionId, command.name === "fork-with-workspace");
        dispatch(upsertSession(forked));
        dispatch(setActiveSession(forked.id));
        // Load the copied history before the optimistic user message so the
        // fetch can't race in afterwards and clobber it.
        await dispatch(loadMessages(forked.id));
        if (args || contentBlocks) {
          dispatch(addUserMessage({ sessionId: forked.id, text: args, contentBlocks }));
          dispatch(setSessionStreaming({ sessionId: forked.id, streaming: true }));
          try {
            await send(args || " ", forked.id, "Medium", contentBlocks);
          } catch {
            // The UI has already switched to the fork; report there, not on
            // the (now hidden) source session.
            dispatch(setSessionStreaming({ sessionId: forked.id, streaming: false }));
            dispatch(setSessionError({ sessionId: forked.id, error: "Failed to connect to server" }));
          }
        }
      }
    },
    [sessionId, dispatch, send],
  );
}
