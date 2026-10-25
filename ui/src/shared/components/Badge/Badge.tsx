import type { ReactNode } from "react";
import styles from "./Badge.module.css";

type BadgeVariant = "primary" | "success" | "warning" | "error" | "muted" | "purple" | "info";

interface BadgeProps {
  variant?: BadgeVariant;
  children: ReactNode;
  mono?: boolean;
  uppercase?: boolean;
  outline?: boolean;
  className?: string;
  style?: React.CSSProperties;
  onClick?: () => void;
  title?: string;
}

export function Badge({
  variant = "muted",
  children,
  mono,
  uppercase,
  outline,
  className,
  style,
  onClick,
  title,
}: BadgeProps) {
  const classes = [
    styles.badge,
    styles[variant],
    mono && styles.mono,
    uppercase && styles.uppercase,
    outline && styles.outline,
    onClick && styles.clickable,
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <span className={classes} style={style} onClick={onClick} title={title}>
      {children}
    </span>
  );
}
