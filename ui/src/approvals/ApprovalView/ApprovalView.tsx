import type { ResolvedApprovalView, ResolvedBlock } from "@/types/api";
import { BlockRenderer } from "./BlockRenderer";
import styles from "./ApprovalView.module.css";

interface ApprovalViewProps {
  view: ResolvedApprovalView;
}

export function ApprovalView({ view }: ApprovalViewProps) {
  if (view.blocks.length === 0) return null;
  return (
    <div className={styles.root}>
      {view.blocks.map((block: ResolvedBlock, i: number) => (
        <BlockRenderer key={i} block={block} />
      ))}
    </div>
  );
}
