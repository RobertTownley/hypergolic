import { useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import { XIcon } from "lucide-react";
import styles from "./ImageModal.module.css";

interface ImageModalProps {
  src: string;
  alt?: string;
  onClose: () => void;
}

export function ImageModal({ src, alt = "Image", onClose }: ImageModalProps) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    },
    [onClose],
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  // Portaled: ancestors with paint containment (content-visibility on ledger
  // turns) would otherwise trap this fixed overlay inside their box.
  return createPortal(
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.content} onClick={(e) => e.stopPropagation()}>
        <img src={src} alt={alt} className={styles.image} />
        <button className={styles.closeButton} onClick={onClose}>
          <XIcon />
        </button>
      </div>
    </div>,
    document.body,
  );
}
