import { FileTextIcon } from "lucide-react";
import type { ContentBlock } from "@/types/api";
import styles from "./attachments.module.css";

function openDocument(block: ContentBlock) {
  const source = block.source!;
  const bytes = Uint8Array.from(atob(source.data), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: source.media_type }));
  window.open(url, "_blank");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export function DocumentThumbnail({ block }: { block: ContentBlock }) {
  if (!block.source) return null;
  return (
    <button type="button" className={styles.documentThumb} onClick={() => openDocument(block)}>
      <FileTextIcon className={styles.documentIcon} />
      <span className={styles.documentLabel}>PDF document</span>
    </button>
  );
}
