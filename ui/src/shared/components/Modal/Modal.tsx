import React, { useRef, useEffect, useCallback, type ReactNode } from "react";
import { XIcon } from "lucide-react";
import styles from "./Modal.module.css";

interface ModalProps {
  onClose: () => void;
  onKeyDown?: (e: React.KeyboardEvent) => void;
  title?: ReactNode;
  icon?: ReactNode;
  width?: number | string;
  maxHeight?: string;
  badge?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
  zIndex?: number;
  className?: string;
  headerExtra?: ReactNode;
}

export function Modal({
  onClose,
  onKeyDown,
  title,
  icon,
  width,
  maxHeight,
  badge,
  footer,
  children,
  zIndex,
  className,
  headerExtra,
}: ModalProps) {
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    overlayRef.current?.focus();
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      e.stopPropagation();
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      onKeyDown?.(e);
    },
    [onClose, onKeyDown],
  );

  const contentStyle: React.CSSProperties = {};
  if (width) contentStyle.width = typeof width === "number" ? `${width}px` : width;
  if (maxHeight) contentStyle.maxHeight = maxHeight;

  return (
    <div
      ref={overlayRef}
      className={styles.overlay}
      style={zIndex ? { zIndex } : undefined}
      onClick={onClose}
      onKeyDown={handleKeyDown}
      tabIndex={-1}
    >
      <div
        className={`${styles.content} ${className ?? ""}`}
        style={contentStyle}
        onClick={(e) => e.stopPropagation()}
      >
        {title !== undefined && (
          <div className={styles.header}>
            <span className={styles.headerTitle}>
              {icon && <span className={styles.headerIcon}>{icon}</span>}
              {title}
            </span>
            {badge}
            {headerExtra}
            <button className={styles.closeButton} onClick={onClose}>
              <XIcon />
            </button>
          </div>
        )}
        <div className={styles.body}>{children}</div>
        {footer && <div className={styles.footer}>{footer}</div>}
      </div>
    </div>
  );
}
