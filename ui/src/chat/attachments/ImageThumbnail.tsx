import { useState } from "react";
import { ImageModal } from "@/modals/ImageModal";
import type { ContentBlock } from "@/types/api";
import styles from "./attachments.module.css";

export function ImageThumbnail({ block }: { block: ContentBlock }) {
  const [modalOpen, setModalOpen] = useState(false);

  if (!block.source) return null;
  const src = `data:${block.source.media_type};base64,${block.source.data}`;

  return (
    <>
      <div className={styles.imageThumbnail} onClick={() => setModalOpen(true)}>
        <img src={src} alt="Attached image" className={styles.thumbnailImg} />
      </div>
      {modalOpen && (
        <ImageModal src={src} alt="Attached image" onClose={() => setModalOpen(false)} />
      )}
    </>
  );
}
