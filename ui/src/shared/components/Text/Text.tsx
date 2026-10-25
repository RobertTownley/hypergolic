import type { CSSProperties, ReactNode } from "react";
import styles from "./Text.module.css";

interface TextProps {
  children?: ReactNode;
  className?: string;
  style?: CSSProperties;
  title?: string;
  /** Semantic colour; omitted = inherit the normal text colour. */
  type?: "danger" | "secondary";
  /** Single line, truncated with an ellipsis. */
  ellipsis?: boolean;
}

export function Text({ children, className, style, title, type, ellipsis }: TextProps) {
  const cls = [styles.text, type && styles[type], ellipsis && styles.ellipsis, className]
    .filter(Boolean)
    .join(" ");
  return <span className={cls} style={style} title={title}>{children}</span>;
}
