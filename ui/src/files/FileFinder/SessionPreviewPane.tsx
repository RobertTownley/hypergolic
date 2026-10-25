import { MessageSquareIcon } from "lucide-react";
import type { Message } from "@/types/api";
import styles from "./FileFinder.module.css";

function extractText(content: unknown[]): string {
  return content
    .map((b) => {
      if (typeof b === "string") return b;
      if (typeof b === "object" && b && "type" in b) {
        const block = b as Record<string, unknown>;
        if (block.type === "text") return String(block.text ?? "");
        if (block.type === "tool_use") return `[tool: ${block.name}]`;
        if (block.type === "tool_result") return "[tool result]";
      }
      return "";
    })
    .filter(Boolean)
    .join("\n");
}

export function SessionPreviewPane({
  messages,
  loading,
  label,
}: {
  messages: Message[] | null;
  loading: boolean;
  label: string | null;
}) {
  if (loading && !messages) {
    return (
      <div className={styles.previewPane}>
        <div className={styles.previewLoading}>Loading\u2026</div>
      </div>
    );
  }

  if (!messages) {
    return (
      <div className={styles.previewPane}>
        <div className={styles.previewEmpty}>No session selected</div>
      </div>
    );
  }

  return (
    <div className={styles.previewPane}>
      <div className={styles.previewHeader}>
        <MessageSquareIcon className={styles.previewHeaderIcon} />
        <span className={styles.previewHeaderPath}>
          {label ?? "Session"}
        </span>
      </div>
      <div className={styles.sessionPreviewContent}>
        {messages.map((msg) => (
          <div key={msg.id} className={styles.sessionMessage}>
            <span className={styles.sessionRole}>{msg.role}</span>
            <span className={styles.sessionText}>
              {extractText(msg.content).slice(0, 500)}
            </span>
          </div>
        ))}
        {messages.length === 0 && (
          <div className={styles.previewEmpty}>No messages</div>
        )}
      </div>
    </div>
  );
}
