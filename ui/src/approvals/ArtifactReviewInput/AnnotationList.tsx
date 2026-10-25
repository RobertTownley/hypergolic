import { Trash2Icon } from "lucide-react";
import type { Annotation } from "@/types/api";
import styles from "./ArtifactReviewInput.module.css";

interface AnnotationListProps {
  annotations: Annotation[];
  onRemove: (id: string) => void;
}

export function AnnotationList({ annotations, onRemove }: AnnotationListProps) {
  if (annotations.length === 0) return null;

  return (
    <div className={styles.annotationsSection}>
      {annotations.map((ann) => (
        <div key={ann.id} className={styles.annotationChip}>
          <span className={styles.annotationHighlight}>"{ann.highlighted_text}"</span>
          <span className={styles.annotationComment}>{ann.comment}</span>
          <button className={styles.annotationRemove} onClick={() => onRemove(ann.id)}>
            <Trash2Icon />
          </button>
        </div>
      ))}
    </div>
  );
}
