import { useState, useMemo, useCallback } from "react";
import type { WorkflowInfo } from "@/types/api";
import { useOnChange } from "@/hooks/useOnChange";
import { useAppDispatch } from "@/store";
import { setDraftText, setDraftWorkflow } from "@/store/uiSlice";
import {
  matchSlashCommands,
  slashMenuQuery,
  workflowMenuQuery,
  type SlashCommand,
} from "./slashCommands";

export interface SlashMenuItem extends SlashCommand {
  workflowId?: string;
}

function menuItems(text: string, workflows: WorkflowInfo[]): SlashMenuItem[] {
  const wfQuery = workflowMenuQuery(text);
  if (wfQuery !== null) {
    return workflows
      .filter((w) => w.name.toLowerCase().includes(wfQuery))
      .map((w) => ({
        name: `workflow ${w.name}`,
        description: w.description ?? "",
        workflowId: w.id,
      }));
  }
  const query = slashMenuQuery(text);
  if (query === null) return [];
  return matchSlashCommands(query).filter(
    (c) => c.name !== "workflow" || workflows.length > 0,
  );
}

export function useSlashMenu(sessionId: string, text: string, workflows: WorkflowInfo[]) {
  const dispatch = useAppDispatch();
  const [index, setIndex] = useState(0);
  const [dismissed, setDismissed] = useState(false);

  const items = useMemo(() => menuItems(text, workflows), [text, workflows]);
  const open = items.length > 0 && !dismissed;
  const selectedIndex = Math.min(index, Math.max(items.length - 1, 0));

  useOnChange(text, () => {
    setIndex(0);
    setDismissed(false);
  });

  const select = useCallback((item: SlashMenuItem) => {
    if (item.workflowId) {
      dispatch(setDraftWorkflow({ sessionId, workflowId: item.workflowId }));
      dispatch(setDraftText({ sessionId, text: "" }));
    } else {
      dispatch(setDraftText({ sessionId, text: `/${item.name} ` }));
    }
  }, [dispatch, sessionId]);

  const handleMenuKey = useCallback((e: React.KeyboardEvent): boolean => {
    if (!open) return false;
    if (e.key === "ArrowDown") {
      setIndex((i) => (i + 1) % items.length);
    } else if (e.key === "ArrowUp") {
      setIndex((i) => (i - 1 + items.length) % items.length);
    } else if (e.key === "Tab" || e.key === "Enter") {
      select(items[selectedIndex]);
    } else if (e.key === "Escape") {
      setDismissed(true);
    } else {
      return false;
    }
    e.preventDefault();
    return true;
  }, [open, items, selectedIndex, select]);

  return { open, items, selectedIndex, setIndex, select, handleMenuKey };
}
