import type { ReactNode } from "react";
import styles from "./ListItem.module.css";

interface ListItemProps {
  children: ReactNode;
  onClick?: () => void;
  selected?: boolean;
  hoverable?: boolean;
  bordered?: boolean;
  actions?: ReactNode;
  meta?: ReactNode;
  className?: string;
  padding?: "compact" | "default";
}

export function ListItem({
  children,
  onClick,
  selected = false,
  hoverable = true,
  bordered = true,
  actions,
  meta,
  className,
  padding = "default",
}: ListItemProps) {
  const classNames = [
    styles.listItem,
    onClick ? styles.clickable : "",
    padding === "compact" ? styles.compact : "",
    bordered ? styles.bordered : "",
    hoverable ? styles.hoverable : "",
    selected ? styles.selected : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  const Tag = onClick ? "button" : "div";

  return (
    <Tag className={classNames} onClick={onClick}>
      {children}
      {meta && <div className={styles.meta}>{meta}</div>}
      {actions && <div className={styles.actions}>{actions}</div>}
    </Tag>
  );
}
