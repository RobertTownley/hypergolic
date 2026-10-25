import { useState, useCallback, useRef } from "react";
import { createPortal } from "react-dom";
import { MessageCircleIcon } from "lucide-react";
import type { Annotation } from "@/types/api";
import styles from "./ArtifactReviewInput.module.css";

let annotationIdCounter = 0;

interface AnnotationLayerProps {
  contentRef: React.RefObject<HTMLDivElement | null>;
  onAdd: (annotation: Annotation) => void;
}


export function useAnnotationLayerWithRef({ contentRef, onAdd }: AnnotationLayerProps) {
  const [selectionRect, setSelectionRect] = useState<{ top: number; left: number } | null>(null);
  const [selectedText, setSelectedText] = useState("");
  const [inputPos, setInputPos] = useState<{ top: number; left: number } | null>(null);
  const [comment, setComment] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleMouseUp = useCallback(() => {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !contentRef.current) {
      setSelectionRect(null);
      setSelectedText("");
      return;
    }

    const text = sel.toString().trim();
    if (!text || !contentRef.current.contains(sel.anchorNode)) {
      setSelectionRect(null);
      setSelectedText("");
      return;
    }

    const range = sel.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    setSelectionRect({ top: rect.bottom + 4, left: rect.left });
    setSelectedText(text);
  }, [contentRef]);

  const handleAddAnnotation = useCallback(() => {
    if (!selectionRect) return;
    setInputPos({ top: selectionRect.top, left: selectionRect.left });
    setComment("");
    setSelectionRect(null);
    setTimeout(() => textareaRef.current?.focus(), 50);
  }, [selectionRect]);

  const handleSave = useCallback(() => {
    if (!comment.trim() || !selectedText) return;
    onAdd({
      id: `ann-${++annotationIdCounter}`,
      highlighted_text: selectedText,
      comment: comment.trim(),
      position: 0,
    });
    setInputPos(null);
    setComment("");
    setSelectedText("");
    window.getSelection()?.removeAllRanges();
  }, [comment, selectedText, onAdd]);

  const handleCancel = useCallback(() => {
    setInputPos(null);
    setComment("");
    window.getSelection()?.removeAllRanges();
  }, []);

  const isInputVisible = !!inputPos;

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (!inputPos) return false;
    if (e.key === "Escape") {
      handleCancel();
      return true;
    }
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      handleSave();
      return true;
    }
    return true;
  }, [inputPos, handleCancel, handleSave]);

  return {
    handleMouseUp,
    handleKeyDown,
    isInputVisible,
    toolbar: selectionRect && !inputPos ? createPortal(
      <div
        className={styles.annotationToolbar}
        style={{ top: selectionRect.top, left: selectionRect.left }}
      >
        <button className={styles.annotationToolbarBtn} onClick={handleAddAnnotation}>
          <MessageCircleIcon /> Add Comment
        </button>
      </div>,
      document.body,
    ) : null,
    input: inputPos ? createPortal(
      <div
        className={styles.annotationInput}
        style={{ top: inputPos.top, left: inputPos.left }}
      >
        <span className={styles.annotationInputLabel}>Comment on:</span>
        <div className={styles.annotationInputQuote}>
          {selectedText.length > 80 ? selectedText.slice(0, 80) + "\u2026" : selectedText}
        </div>
        <textarea
          ref={textareaRef}
          className={styles.annotationTextarea}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Your comment..."
          rows={2}
        />
        <div className={styles.annotationInputActions}>
          <button
            className={`${styles.annotationInputBtn} ${styles.annotationInputCancel}`}
            onClick={handleCancel}
          >
            Cancel
          </button>
          <button
            className={`${styles.annotationInputBtn} ${styles.annotationInputSave}`}
            onClick={handleSave}
            disabled={!comment.trim()}
          >
            Save (⌘↵)
          </button>
        </div>
      </div>,
      document.body,
    ) : null,
  };
}
