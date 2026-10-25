import type { ReactElement, ReactNode } from "react";
import * as Radix from "@radix-ui/react-dropdown-menu";
import styles from "./DropdownMenu.module.css";

export type MenuItem =
  | { key: string; label: ReactNode; icon?: ReactNode; onClick?: () => void; danger?: boolean }
  | { type: "divider" };

interface DropdownMenuProps {
  items: MenuItem[];
  align?: "start" | "center" | "end";
  /** Must be a single element that can hold a ref (e.g. a <button>). */
  children: ReactElement;
}

export function DropdownMenu({ items, align = "end", children }: DropdownMenuProps) {
  return (
    <Radix.Root modal={false}>
      <Radix.Trigger asChild>{children}</Radix.Trigger>
      <Radix.Portal>
        <Radix.Content align={align} sideOffset={4} collisionPadding={8} className={styles.content}>
          {items.map((item, i) =>
            "type" in item ? (
              <Radix.Separator key={`divider-${i}`} className={styles.divider} />
            ) : (
              <Radix.Item
                key={item.key}
                className={`${styles.item} ${item.danger ? styles.danger : ""}`}
                onSelect={item.onClick}
              >
                {item.icon && <span className={styles.icon}>{item.icon}</span>}
                <span>{item.label}</span>
              </Radix.Item>
            ),
          )}
        </Radix.Content>
      </Radix.Portal>
    </Radix.Root>
  );
}
