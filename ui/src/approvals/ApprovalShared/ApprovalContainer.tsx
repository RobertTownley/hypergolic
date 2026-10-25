import { useEffect, useRef, useImperativeHandle, type Ref } from "react";
import styles from "./ApprovalShared.module.css";

interface ApprovalContainerProps {
  onKeyDown: (e: React.KeyboardEvent) => void;
  ariaLabel: string;
  className?: string;
  children: React.ReactNode;
  ref?: Ref<ApprovalContainerHandle>;
}

interface ApprovalContainerHandle {
  focus: () => void;
}

export function ApprovalContainer({
  onKeyDown,
  ariaLabel,
  className,
  children,
  ref,
}: ApprovalContainerProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useImperativeHandle(ref, () => ({
    focus: () => containerRef.current?.focus(),
  }));

  useEffect(() => {
    containerRef.current?.focus();
  }, []);

  return (
    <div
      className={`${styles.container} ${className ?? ""}`}
      onKeyDown={onKeyDown}
      tabIndex={-1}
      ref={containerRef}
      role="region"
      aria-label={ariaLabel}
    >
      {children}
    </div>
  );
}
