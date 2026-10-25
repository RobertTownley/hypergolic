import { WrenchIcon } from "lucide-react";
import { Chip } from "@/shared/components";
import styles from "./ApprovalShared.module.css";

interface ApprovalHeaderProps {
  label: string;
  toolName: string;
  /** Slot for inline content (e.g. annotation count) adjacent to the tool tag. */
  children?: React.ReactNode;
  /** Right-aligned slot, typically the raw-JSON / rendered toggle. */
  rightSlot?: React.ReactNode;
}

export function ApprovalHeader({ label, toolName, children, rightSlot }: ApprovalHeaderProps) {
  return (
    <div className={styles.header}>
      <WrenchIcon className={styles.toolIcon} />
      <span className={styles.label}>{label}</span>
      <Chip tone="tool">{toolName}</Chip>
      {children}
      {rightSlot && <div className={styles.headerRight}>{rightSlot}</div>}
    </div>
  );
}
