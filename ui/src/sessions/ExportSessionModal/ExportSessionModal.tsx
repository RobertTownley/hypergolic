import { useState, useCallback } from "react";
import { DownloadIcon, FileImageIcon, LoaderCircleIcon } from "lucide-react";
import { Modal } from "@/shared/components/Modal";
import { useLedgerContext } from "@/chat/Ledger";
import styles from "./ExportSessionModal.module.css";

interface ExportSessionModalProps {
  sessionId: string;
  onClose: () => void;
}

export function ExportSessionModal({ sessionId, onClose }: ExportSessionModalProps) {
  const { viewportRef } = useLedgerContext();
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleExportWebP = useCallback(async () => {
    const el = viewportRef.current;
    if (!el) return;

    setExporting(true);
    setError(null);

    const prevOverflow = el.style.overflowY;
    const prevHeight = el.style.height;
    try {
      const { domToBlob } = await import("modern-screenshot");

      // Temporarily expand the scrollable container to full scroll height
      // so the capture includes the entire message history.
      el.style.overflowY = "visible";
      el.style.height = `${el.scrollHeight}px`;

      const blob = await domToBlob(el, {
        type: "image/webp",
        quality: 0.92,
        scale: window.devicePixelRatio ?? 1,
        width: el.offsetWidth,
        height: el.scrollHeight,
      });

      if (!blob) throw new Error("Failed to encode WebP");

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `session-${sessionId.slice(0, 8)}.webp`;
      a.click();
      URL.revokeObjectURL(url);

      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    } finally {
      el.style.overflowY = prevOverflow;
      el.style.height = prevHeight;
      setExporting(false);
    }
  }, [viewportRef, sessionId, onClose]);

  return (
    <Modal
      onClose={onClose}
      title="Export Session"
      icon={<DownloadIcon />}
      width={360}
    >
      <div className={styles.body}>
        <button
          className={styles.optionBtn}
          onClick={handleExportWebP}
          disabled={exporting}
        >
          {exporting ? (
            <LoaderCircleIcon className={`icon-spin ${styles.optionIcon}`} />
          ) : (
            <FileImageIcon className={styles.optionIcon} />
          )}
          <div className={styles.optionText}>
            <span className={styles.optionLabel}>WebP Image</span>
            <span className={styles.optionDesc}>
              Full message history as a screenshot
            </span>
          </div>
        </button>

        {error && <p className={styles.error}>{error}</p>}
      </div>
    </Modal>
  );
}
