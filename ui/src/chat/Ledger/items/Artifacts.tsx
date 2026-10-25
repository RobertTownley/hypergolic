import { Base64Image } from "@/shared/components";
import type { ContentBlock } from "@/types/api";
import styles from "./items.module.css";

export function Artifacts({ images }: { images?: ContentBlock[] }) {
  if (!images?.length) return null;
  return (
    <div className={styles.artifacts}>
      {images.map((image, i) => (
        <Base64Image key={i} block={image} alt="Tool result" className={styles.thumb} />
      ))}
    </div>
  );
}
