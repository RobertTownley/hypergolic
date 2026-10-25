import { FlaskConicalIcon, GitBranchIcon, PlugIcon, UserIcon, WorkflowIcon, WrenchIcon, ZapIcon } from "lucide-react";
import type { ToolInfo } from "@/types/api";

export interface ToolGroup {
  key: string;
  label: string;
  icon: React.ReactNode;
  reason: string;
  tools: ToolInfo[];
}

function reasonLabel(reason: string): { key: string; label: string; icon: React.ReactNode } {
  if (reason === "app") return { key: "app", label: "Built-in", icon: <ZapIcon /> };
  if (reason === "project") return { key: "project", label: "Project", icon: <WrenchIcon /> };
  if (reason === "role") return { key: "role", label: "Role", icon: <UserIcon /> };
  if (reason.startsWith("skill:")) {
    const id = reason.slice(6);
    return { key: reason, label: `Skill: ${id}`, icon: <FlaskConicalIcon /> };
  }
  if (reason.startsWith("workflow:")) {
    const id = reason.slice(9);
    return { key: reason, label: `Workflow: ${id}`, icon: <GitBranchIcon /> };
  }
  if (reason.startsWith("workflow_state:")) {
    const id = reason.slice(15);
    return { key: reason, label: `State: ${id}`, icon: <WorkflowIcon /> };
  }
  if (reason.startsWith("mcp:")) {
    const server = reason.slice(4);
    return { key: reason, label: server, icon: <PlugIcon /> };
  }
  return { key: reason, label: reason, icon: <WrenchIcon /> };
}

export function groupTools(tools: ToolInfo[]): ToolGroup[] {
  const groupMap = new Map<string, { label: string; icon: React.ReactNode; reason: string; tools: ToolInfo[] }>();
  const groupOrder: string[] = [];

  for (const tool of tools) {
    const { key, label, icon } = reasonLabel(tool.reason);
    if (!groupMap.has(key)) {
      groupMap.set(key, { label, icon, reason: tool.reason, tools: [] });
      groupOrder.push(key);
    }
    groupMap.get(key)!.tools.push(tool);
  }

  return groupOrder.map((key) => {
    const g = groupMap.get(key)!;
    return { key, label: g.label, icon: g.icon, reason: g.reason, tools: g.tools };
  });
}
