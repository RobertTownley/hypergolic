import type { HTMLAttributes, ReactNode } from "react";
import styles from "./Card.module.css";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  hoverable?: boolean;
  padding?: "none" | "compact" | "default";
  onClick?: () => void;
  className?: string;
}

const paddingClass = {
  none: styles.paddingNone,
  compact: styles.paddingCompact,
  default: styles.paddingDefault,
};

export function Card({
  children,
  hoverable = false,
  padding = "default",
  onClick,
  className,
  ...rest
}: CardProps) {
  const classes = [
    styles.card,
    paddingClass[padding],
    hoverable ? styles.hoverable : "",
    onClick ? styles.clickable : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={classes} onClick={onClick} {...rest}>
      {children}
    </div>
  );
}
