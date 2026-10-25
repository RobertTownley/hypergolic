import type { ReactNode, ButtonHTMLAttributes } from "react";
import styles from "./Button.module.css";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "small" | "medium" | "large";
  icon?: ReactNode;
  iconPosition?: "left" | "right";
  loading?: boolean;
  fullWidth?: boolean;
}

export function Button({
  children,
  variant = "secondary",
  size = "medium",
  icon,
  iconPosition = "left",
  loading = false,
  fullWidth = false,
  className,
  disabled,
  ...props
}: ButtonProps) {
  const classNames = [
    styles.button,
    styles[variant],
    styles[size],
    fullWidth ? styles.fullWidth : "",
    loading ? styles.loading : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button className={classNames} disabled={disabled || loading} {...props}>
      {icon && iconPosition === "left" && <span className={styles.icon}>{icon}</span>}
      {children && <span className={styles.content}>{children}</span>}
      {icon && iconPosition === "right" && <span className={styles.icon}>{icon}</span>}
    </button>
  );
}

