import { useRef, useCallback, useEffect, useLayoutEffect } from "react";
import type { ContentBlock, ModelTier } from "@/types/api";
import { useAppSelector, useAppDispatch } from "@/store";
import { FOCUS_CHAT_EVENT } from "@/hooks/useKeyboardShortcuts";
import { setSessionError } from "@/store/messagesSlice";
import { parseSlashCommand } from "./slashCommands";
import { useSlashCommands } from "./useSlashCommands";
import { useSlashMenu } from "./useSlashMenu";
import { useAttachments } from "./useAttachments";
import { useWorkflows } from "./useWorkflows";
import {
  selectDraft,
  setDraftText,
  setDraftWorkflow,
  clearDraft,
} from "@/store/uiSlice";

const MAX_TEXTAREA_HEIGHT = 84; /* 4 lines @ 14px * 1.5; keep in sync with .textarea max-height */

interface UseChatInputArgs {
  sessionId: string;
  onSend: (message: string, modelTier: ModelTier, contentBlocks?: ContentBlock[], workflowId?: string) => void;
}

function attachmentBlocks(attachments: ReturnType<typeof useAttachments>["allAttachments"]): ContentBlock[] {
  return attachments.map((a) => {
    if (a.type === "summary_recall") {
      return { type: "summary_recall" as const, text: a.content };
    }
    if (a.type === "code_selection") {
      const { filePath, startLine, endLine, content, language } = a.selection;
      const header = startLine === endLine
        ? `File: ${filePath}, Line ${startLine}`
        : `File: ${filePath}, Lines ${startLine}-${endLine}`;
      return {
        type: "text" as const,
        text: `[Code Selection] ${header}\n\`\`\`${language}\n${content}\n\`\`\``,
      };
    }
    return { type: a.type, source: a.source };
  });
}

export function useChatInput({ sessionId, onSend }: UseChatInputArgs) {
  const dispatch = useAppDispatch();
  const { text, workflowId } = useAppSelector((s) => selectDraft(s, sessionId));
  const activeSessionId = useAppSelector((s) => s.sessions.activeSessionId);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const focusTextarea = useCallback(() => textareaRef.current?.focus(), []);

  const workflows = useWorkflows(sessionId);
  const menu = useSlashMenu(sessionId, text, workflows);
  const attachments = useAttachments(sessionId, focusTextarea);

  useEffect(() => {
    if (activeSessionId) focusTextarea();
  }, [activeSessionId, focusTextarea]);

  useEffect(() => {
    window.addEventListener(FOCUS_CHAT_EVENT, focusTextarea);
    return () => window.removeEventListener(FOCUS_CHAT_EVENT, focusTextarea);
  }, [focusTextarea]);

  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT)}px`;
  }, [text]);

  const runSlashCommand = useSlashCommands(sessionId);

  const selectWorkflow = useCallback((args: string) => {
    const wf = workflows.find((w) => w.name.toLowerCase() === args.toLowerCase());
    if (!wf) {
      dispatch(setSessionError({ sessionId, error: `Unknown workflow: ${args}` }));
      return;
    }
    dispatch(setDraftWorkflow({ sessionId, workflowId: wf.id }));
    dispatch(setDraftText({ sessionId, text: "" }));
  }, [workflows, sessionId, dispatch]);

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed && attachments.allAttachments.length === 0) return;

    const contentBlocks = attachmentBlocks(attachments.allAttachments);
    const blocks = contentBlocks.length > 0 ? contentBlocks : undefined;

    const slash = parseSlashCommand(trimmed);
    if (slash?.command.name === "workflow") {
      selectWorkflow(slash.args);
      return;
    }
    if (slash) {
      // Clear the draft only once the command lands; a failed fork keeps the
      // typed message and surfaces the error on this session.
      runSlashCommand(slash.command, slash.args, blocks)
        .then(() => dispatch(clearDraft(sessionId)))
        .catch((err: unknown) => {
          dispatch(setSessionError({
            sessionId,
            error: err instanceof Error ? err.message : "Command failed",
          }));
        });
      return;
    }

    onSend(trimmed || " ", "Medium", blocks, workflowId ?? undefined);
    dispatch(clearDraft(sessionId));
  }, [text, onSend, attachments.allAttachments, workflowId, sessionId, dispatch, runSlashCommand, selectWorkflow]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (menu.handleMenuKey(e)) return;
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleTextChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    dispatch(setDraftText({ sessionId, text: e.target.value }));
  };

  const clearWorkflow = () => dispatch(setDraftWorkflow({ sessionId, workflowId: null }));

  const openFilePicker = () => fileInputRef.current?.click();

  return {
    text,
    selectedWorkflow: workflows.find((w) => w.id === workflowId) ?? null,
    menu,
    ...attachments,
    textareaRef,
    fileInputRef,
    handleSend,
    handleKeyDown,
    handleTextChange,
    clearWorkflow,
    openFilePicker,
  };
}
