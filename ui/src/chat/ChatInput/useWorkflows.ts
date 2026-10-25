import { useState, useEffect } from "react";
import { fetchWorkflows } from "@/api/sessions";
import { useAppSelector } from "@/store";
import type { WorkflowInfo } from "@/types/api";

export function useWorkflows(sessionId: string): WorkflowInfo[] {
  const [workflows, setWorkflows] = useState<WorkflowInfo[]>([]);
  const activeWorkflowId = useAppSelector(
    (s) => s.sessions.entities[sessionId]?.workflow_id,
  );

  useEffect(() => {
    if (activeWorkflowId) return;
    fetchWorkflows(sessionId)
      .then(setWorkflows)
      .catch(() => setWorkflows([]));
  }, [sessionId, activeWorkflowId]);

  return activeWorkflowId ? [] : workflows;
}
