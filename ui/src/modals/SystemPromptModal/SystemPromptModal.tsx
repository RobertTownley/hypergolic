import { FileTextIcon } from "lucide-react";
import { MarkdownContent } from "@/chat/MarkdownContent";
import { Modal } from "@/shared/components/Modal";
import styles from "./SystemPromptModal.module.css";

interface PromptPart {
  source: string;
  content: string;
  token_estimate: number;
}

interface SystemPromptModalProps {
  parts: PromptPart[];
  totalTokens: number;
  onClose: () => void;
}

function formatCount(n: number) {
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toString();
}

export function SystemPromptModal({ parts, totalTokens, onClose }: SystemPromptModalProps) {
  return (
    <Modal
      onClose={onClose}
      title={`System Prompt (~${formatCount(totalTokens)} tok)`}
      icon={<FileTextIcon />}
      width={720}
      maxHeight="85vh"
    >
      <div className={styles.sections}>
        {parts.map((part, i) => (
          <div key={i} className={styles.section}>
            <div className={styles.sectionHeader}>
              <span className={styles.sectionSource}>{part.source}</span>
              <span className={styles.sectionTokens}>~{formatCount(part.token_estimate)} tok</span>
            </div>
            <div className={styles.sectionContent}>
              <MarkdownContent text={part.content} />
            </div>
          </div>
        ))}
      </div>
    </Modal>
  );
}
