import { useState } from "react";
import { SquareTerminalIcon } from "lucide-react";
import { CodeSelectionModal } from "@/modals/CodeSelectionModal";
import type { CodeSelection } from "@/types/api";
import styles from "./attachments.module.css";

export function CodeSelectionThumbnail({ selection }: { selection: CodeSelection }) {
  const [modalOpen, setModalOpen] = useState(false);
  const filename = selection.filePath.split("/").pop() ?? selection.filePath;
  const lineLabel =
    selection.startLine === selection.endLine
      ? `L${selection.startLine}`
      : `L${selection.startLine}-${selection.endLine}`;
  const previewLines = selection.content.split("\n").slice(0, 4).join("\n");

  return (
    <>
      <div className={styles.codeSelectionThumb} onClick={() => setModalOpen(true)}>
        <div className={styles.codeSelectionHeader}>
          <SquareTerminalIcon className={styles.codeSelectionIcon} />
          <span className={styles.codeSelectionFilename}>{filename}</span>
          <span className={styles.codeSelectionLines}>{lineLabel}</span>
        </div>
        <pre className={styles.codeSelectionPreview}>{previewLines}</pre>
      </div>
      {modalOpen && (
        <CodeSelectionModal selection={selection} onClose={() => setModalOpen(false)} />
      )}
    </>
  );
}
