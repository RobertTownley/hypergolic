import type { ReactNode, HTMLAttributes, Ref } from "react";
import styles from "./Panel.module.css";

interface PanelProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  fullHeight?: boolean;
  ref?: Ref<HTMLDivElement>;
}

export function Panel({ children, className, fullHeight = true, ref, ...rest }: PanelProps) {
  return (
    <div
      ref={ref}
      className={`${styles.panel} ${fullHeight ? styles.fullHeight : ""} ${className ?? ""}`}
      {...rest}
    >
      {children}
    </div>
  );
}

interface PanelHeaderProps {
  children: ReactNode;
  className?: string;
  icon?: ReactNode;
  actions?: ReactNode;
}

export function PanelHeader({ children, className, icon, actions }: PanelHeaderProps) {
  return (
    <div className={`${styles.header} ${className ?? ""}`}>
      {icon && <span className={styles.headerIcon}>{icon}</span>}
      <span className={styles.headerTitle}>{children}</span>
      {actions && <div className={styles.headerActions}>{actions}</div>}
    </div>
  );
}

interface PanelBodyProps {
  children: ReactNode;
  className?: string;
  scrollable?: boolean;
}

export function PanelBody({ children, className, scrollable = false }: PanelBodyProps) {
  return (
    <div className={`${styles.body} ${scrollable ? styles.scrollable : ""} ${className ?? ""}`}>
      {children}
    </div>
  );
}


