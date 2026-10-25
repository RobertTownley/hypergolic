import { WorkflowIcon } from "lucide-react";
import styles from "./items.module.css";

interface TransitionProps {
  workflowName?: string;
  stateName?: string;
  toolName: string;
}

/** A workflow moved to a new state: a divider, not a tool call. */
export function Transition({ workflowName, stateName, toolName }: TransitionProps) {
  const label = workflowName ?? (toolName === "activate_workflow" ? "workflow" : toolName);
  return (
    <div className={styles.transition}>
      <span className={styles.transitionPill}>
        <WorkflowIcon />
        <b>{label}</b>
        {stateName && <>→ {stateName}</>}
      </span>
    </div>
  );
}
