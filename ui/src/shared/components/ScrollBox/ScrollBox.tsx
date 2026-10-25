import type { ReactNode } from "react";
import { cx } from "@/utils/cx";
import styles from "./ScrollBox.module.css";

interface ScrollBoxProps {
  /** Visible height, in lines of the box's own line-height. */
  lines: number;
  className?: string;
  children: ReactNode;
}

/**
 * A bounded scroll region: the only place in the ledger where content grows.
 *
 * Height is stated in lines and never in payload size, so a row's geometry is
 * the same whether a command printed four lines or four thousand. That is what
 * keeps the transcript's scroll position stable.
 */
export function ScrollBox({ lines, className, children }: ScrollBoxProps) {
  return (
    <div className={cx(styles.box, className)} style={{ "--sb-lines": lines } as React.CSSProperties}>
      <div>{children}</div>
    </div>
  );
}
