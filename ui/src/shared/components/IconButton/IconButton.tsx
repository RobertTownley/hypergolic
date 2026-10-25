import type { ReactNode, ButtonHTMLAttributes } from "react";
import styles from "./IconButton.module.css";

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: ReactNode;
  variant?: "ghost" | "danger";
  size?: "small" | "medium";
  tooltip?: string;
}

export function IconButton({
  icon,
  variant = "ghost",
  size = "small",
  tooltip,
  className,
  ...props
}: IconButtonProps) {
  const classNames = [
    styles.iconButton,
    styles[variant],
    styles[size],
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button className={classNames} title={tooltip} {...props}>
      {icon}
    </button>
  );
}
