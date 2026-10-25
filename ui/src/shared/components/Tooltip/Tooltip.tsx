import type { ReactElement, ReactNode } from "react";
import * as RadixTooltip from "@radix-ui/react-tooltip";
import styles from "./Tooltip.module.css";

interface TooltipProps {
  title: ReactNode;
  placement?: "top" | "right" | "bottom" | "left";
  /** Must be a single element that can hold a ref (e.g. a <button>). */
  children: ReactElement;
}

export function Tooltip({ title, placement = "top", children }: TooltipProps) {
  if (title === null || title === undefined || title === "") return children;
  return (
    <RadixTooltip.Provider delayDuration={100} skipDelayDuration={300}>
      <RadixTooltip.Root>
        <RadixTooltip.Trigger asChild>{children}</RadixTooltip.Trigger>
        <RadixTooltip.Portal>
          <RadixTooltip.Content side={placement} sideOffset={6} collisionPadding={8} className={styles.content}>
            {title}
            <RadixTooltip.Arrow className={styles.arrow} width={10} height={5} />
          </RadixTooltip.Content>
        </RadixTooltip.Portal>
      </RadixTooltip.Root>
    </RadixTooltip.Provider>
  );
}
