import type { ReactNode } from "react";
import styles from "./EmptyState.module.css";

interface EmptyStateProps {
  icon?: ReactNode;
  text?: ReactNode;
  children?: ReactNode;
  className?: string;
}

export function EmptyState({ icon, text, children, className }: EmptyStateProps) {
  return (
    <div className={`${styles.emptyState} ${className ?? ""}`}>
      {icon && <span className={styles.icon}>{icon}</span>}
      {text && <span className={styles.text}>{text}</span>}
      {children}
    </div>
  );
}
