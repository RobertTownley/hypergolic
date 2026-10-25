import { useCallback, useMemo, useState } from "react";
import type { ToolInfo } from "@/types/api";
import { groupTools } from "./groupTools";
import type { ToolGroup } from "./groupTools";

interface UseToolsModalParams {
  tools: ToolInfo[];
}

interface UseToolsModalResult {
  expandedTools: Set<string>;
  collapsedGroups: Set<string>;
  groups: ToolGroup[];
  toggleTool: (id: string) => void;
  toggleGroup: (key: string) => void;
}

export function useToolsModal({ tools }: UseToolsModalParams): UseToolsModalResult {
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set());
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());

  const groups = useMemo(() => groupTools(tools), [tools]);

  const toggleTool = useCallback((id: string) => {
    setExpandedTools((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleGroup = useCallback((key: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  return {
    expandedTools,
    collapsedGroups,
    groups,
    toggleTool,
    toggleGroup,
  };
}
