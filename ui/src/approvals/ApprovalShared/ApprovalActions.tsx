import { useState } from "react";
import { Button } from "@/shared/components/Button";
import { BanIcon, CheckIcon, XIcon } from "lucide-react";
import styles from "./ApprovalShared.module.css";
import type { PendingKey } from "@/approvals/usePendingKeyShortcuts";

export interface ApprovalActionButton {
  key: string;
  label: string;
  shortcut: string;
  icon: React.ReactNode;
  onClick: () => void;
  variant?: "approve" | "deny" | "secondary";
  pushRight?: boolean;
}

interface ApprovalActionsProps {
  onApprove: () => void;
  onDeny: (reason?: string) => void;
  extraButtons?: ApprovalActionButton[];
  pendingKey?: PendingKey;
  showDenyInput?: boolean;
  onShowDenyInputChange?: (show: boolean) => void;
}

export function ApprovalActions({
  onApprove,
  onDeny,
  extraButtons,
  pendingKey,
  showDenyInput: showDenyInputProp,
  onShowDenyInputChange,
}: ApprovalActionsProps) {
  const [showDenyInputLocal, setShowDenyInputLocal] = useState(false);
  const showDenyInput = showDenyInputProp ?? showDenyInputLocal;
  const setShowDenyInput = onShowDenyInputChange ?? setShowDenyInputLocal;
  const [denyReason, setDenyReason] = useState("");

  const handleDenyWithReason = () => {
    onDeny(denyReason.trim() || undefined);
    setShowDenyInput(false);
    setDenyReason("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleDenyWithReason();
    }
    if (e.key === "Escape") {
      e.preventDefault();
      setShowDenyInput(false);
      setDenyReason("");
    }
  };

  if (showDenyInput) {
    return (
      <div className={styles.denyInputRow}>
        <input
          className={styles.denyInput}
          value={denyReason}
          onChange={(e) => setDenyReason(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Reason for denial (optional, Enter to submit)"
          autoFocus
        />
        <Button size="small" variant="ghost" icon={<BanIcon />} className={styles.denyButton} onClick={handleDenyWithReason}>
          Deny
        </Button>
        <Button size="small" variant="secondary" onClick={() => { setShowDenyInput(false); setDenyReason(""); }}>
          Cancel
        </Button>
      </div>
    );
  }

  const variantClass = (variant?: string) => {
    switch (variant) {
      case "approve": return styles.approveButton;
      case "secondary": return styles.secondaryButton;
      default: return "";
    }
  };

  const pendingHint = (key: string) =>
    pendingKey?.toLowerCase() === key.toLowerCase()
      ? <span className={styles.pendingHint}>→ Enter</span>
      : null;

  return (
    <div className={styles.actions}>
      <Button
        variant="primary"
        icon={<CheckIcon />}
        onClick={onApprove}
        className={`${styles.approveButton}${pendingKey === "y" ? " " + styles.pendingButton : ""}`}
      >
        Approve <span className={styles.shortcutHint}>Y</span>{pendingHint("y")}
      </Button>
      <Button
        icon={<XIcon />}
        onClick={() => onDeny()}
        variant="ghost"
        className={`${styles.denyButton}${pendingKey === "n" ? " " + styles.pendingButton : ""}`}
      >
        Deny <span className={styles.shortcutHint}>N</span>{pendingHint("n")}
      </Button>
      <Button
        variant="secondary"
        icon={<BanIcon />}
        onClick={() => setShowDenyInput(true)}
        className={`${styles.secondaryButton}${pendingKey === "d" ? " " + styles.pendingButton : ""}`}
      >
        Deny with Message <span className={styles.shortcutHint}>D</span>{pendingHint("d")}
      </Button>
      {extraButtons?.map((btn) => (
        <Button
          key={btn.key}
          variant="secondary"
          icon={btn.icon}
          onClick={btn.onClick}
          className={`${variantClass(btn.variant)}${btn.pushRight ? " " + styles.pushRight : ""}${pendingKey?.toLowerCase() === btn.shortcut.toLowerCase() ? " " + styles.pendingButton : ""}`}
        >
          {btn.label} <span className={styles.shortcutHint}>{btn.shortcut}</span>{pendingHint(btn.shortcut)}
        </Button>
      ))}
    </div>
  );
}


