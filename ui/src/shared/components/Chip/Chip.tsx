import type { ReactNode } from "react";
import { cx } from "@/utils/cx";
import styles from "./Chip.module.css";

type ChipTone = "neutral" | "ok" | "error" | "warning" | "info" | "tool";

interface ChipProps {
  tone?: ChipTone;
  className?: string;
  children: ReactNode;
}

/** Small monospace status/metric label. */
export function Chip({ tone = "neutral", className, children }: ChipProps) {
  return <span className={cx(styles.chip, styles[tone], className)}>{children}</span>;
}
