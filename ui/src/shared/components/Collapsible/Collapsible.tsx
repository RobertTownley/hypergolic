import { useState } from "react";
import type { ReactNode } from "react";
import { ChevronRightIcon } from "lucide-react";
import styles from "./Collapsible.module.css";

interface CollapsibleProps {
  icon?: ReactNode;
  title: string;
  children: ReactNode;
  defaultExpanded?: boolean;
  expanded?: boolean;
  onToggle?: (expanded: boolean) => void;
  className?: string;
  headerClassName?: string;
  bodyClassName?: string;
  borderTop?: boolean;
}

export function Collapsible({
  icon,
  title,
  children,
  defaultExpanded = true,
  expanded: controlledExpanded,
  onToggle,
  className,
  headerClassName,
  bodyClassName,
  borderTop = true,
}: CollapsibleProps) {
  const [uncontrolledExpanded, setUncontrolledExpanded] = useState(defaultExpanded);
  const isControlled = controlledExpanded !== undefined;
  const isExpanded = isControlled ? controlledExpanded : uncontrolledExpanded;

  const handleToggle = () => {
    const next = !isExpanded;
    if (isControlled) {
      onToggle?.(next);
    } else {
      setUncontrolledExpanded(next);
      onToggle?.(next);
    }
  };

  return (
    <div className={`${styles.section} ${borderTop ? styles.borderTop : ""} ${className ?? ""}`}>
      <button className={`${styles.header} ${headerClassName ?? ""}`} onClick={handleToggle}>
        <div className={styles.headerLeft}>
          {icon && <span className={styles.icon}>{icon}</span>}
          <span>{title}</span>
        </div>
        <ChevronRightIcon
          className={styles.chevron}
          style={{ transform: isExpanded ? "rotate(90deg)" : "rotate(0deg)" }}
        />
      </button>
      {isExpanded && (
        <div className={`${styles.body} ${bodyClassName ?? ""}`}>
          {children}
        </div>
      )}
    </div>
  );
}
