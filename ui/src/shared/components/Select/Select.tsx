import * as Radix from "@radix-ui/react-select";
import { ChevronDownIcon } from "lucide-react";
import styles from "./Select.module.css";

export interface SelectOption<T extends string | number> {
  label: string;
  value: T;
}

interface SelectProps<T extends string | number> {
  value: T;
  options: SelectOption<T>[];
  onChange: (value: T) => void;
  className?: string;
  "aria-label"?: string;
}

/**
 * Radix Select forbids "" as an item value, so items are keyed by index and
 * mapped back to the caller's value.
 */
export function Select<T extends string | number>({
  value, options, onChange, className, "aria-label": ariaLabel,
}: SelectProps<T>) {
  const index = options.findIndex((o) => o.value === value);
  return (
    <Radix.Root
      value={index >= 0 ? String(index) : undefined}
      onValueChange={(i) => onChange(options[Number(i)].value)}
    >
      <Radix.Trigger className={`${styles.trigger} ${className ?? ""}`} aria-label={ariaLabel}>
        <Radix.Value />
        <Radix.Icon className={styles.chevron}><ChevronDownIcon /></Radix.Icon>
      </Radix.Trigger>
      <Radix.Portal>
        <Radix.Content position="popper" sideOffset={4} collisionPadding={8} className={styles.content}>
          <Radix.Viewport>
            {options.map((o, i) => (
              <Radix.Item key={String(o.value)} value={String(i)} className={styles.item}>
                <Radix.ItemText>{o.label}</Radix.ItemText>
              </Radix.Item>
            ))}
          </Radix.Viewport>
        </Radix.Content>
      </Radix.Portal>
    </Radix.Root>
  );
}
