import { Spinner } from "@/shared/components/Spinner";
import { FileTextIcon, ShrinkIcon, SquareTerminalIcon, Trash2Icon } from "lucide-react";
import type { Attachment } from "@/types/api";
import styles from "./ChatInput.module.css";

interface AttachmentBarProps {
  attachments: Attachment[];
  uploading: boolean;
  onPreview: (a: Attachment) => void;
  onRemove: (id: string) => void;
}

function Thumb({ attachment, onPreview }: { attachment: Attachment; onPreview: (a: Attachment) => void }) {
  if (attachment.type === "document") {
    return (
      <div className={styles.codeThumb} aria-label={attachment.filename} title={attachment.filename}>
        <FileTextIcon style={{ fontSize: 16, color: "#f87171" }} />
        <span className={styles.codeThumbLabel}>{attachment.filename}</span>
      </div>
    );
  }
  if (attachment.type === "image") {
    return (
      <button
        type="button"
        className={styles.thumbImageButton}
        onClick={() => onPreview(attachment)}
        aria-label={`Preview ${attachment.filename}`}
      >
        <img src={attachment.preview} alt={attachment.filename} className={styles.thumbImage} />
      </button>
    );
  }
  if (attachment.type === "summary_recall") {
    return (
      <div className={styles.codeThumb} aria-label="Unsummarized content" title="Original content of a summarized turn">
        <ShrinkIcon style={{ fontSize: 16, color: "#fbbf24" }} />
        <span className={styles.codeThumbLabel}>unsummarized content</span>
      </div>
    );
  }
  const { filePath, startLine, endLine } = attachment.selection;
  return (
    <button
      type="button"
      className={styles.codeThumb}
      onClick={() => onPreview(attachment)}
      aria-label={`Preview ${filePath} lines ${startLine}-${endLine}`}
    >
      <SquareTerminalIcon style={{ fontSize: 16, color: "#818cf8" }} />
      <span className={styles.codeThumbLabel}>{filePath.split("/").pop()}</span>
      <span className={styles.codeThumbLines}>
        L{startLine}{startLine !== endLine ? `-${endLine}` : ""}
      </span>
    </button>
  );
}

export function AttachmentBar({ attachments, uploading, onPreview, onRemove }: AttachmentBarProps) {
  if (attachments.length === 0 && !uploading) return null;
  return (
    <div className={styles.attachmentBar}>
      {attachments.map((a) => (
        <div key={a.id} className={styles.attachmentThumb}>
          <Thumb attachment={a} onPreview={onPreview} />
          <button
            className={styles.thumbRemove}
            onClick={() => onRemove(a.id)}
            aria-label="Remove attachment"
          >
            <Trash2Icon style={{ fontSize: 10 }} />
          </button>
        </div>
      ))}
      {uploading && (
        <div className={styles.attachmentThumb}>
          <div className={styles.thumbLoading}>
            <Spinner size="small" />
          </div>
        </div>
      )}
    </div>
  );
}
