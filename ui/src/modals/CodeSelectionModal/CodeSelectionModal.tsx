import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { codeTheme } from "@/shared/codeTheme";
import type { CodeSelection } from "@/types/api";
import { Modal } from "@/shared/components/Modal";
import styles from "./CodeSelectionModal.module.css";

interface CodeSelectionModalProps {
  selection: CodeSelection;
  onClose: () => void;
}

export function CodeSelectionModal({ selection, onClose }: CodeSelectionModalProps) {
  const lineRange = selection.startLine === selection.endLine
    ? `Line ${selection.startLine}`
    : `Lines ${selection.startLine}-${selection.endLine}`;

  return (
    <Modal
      onClose={onClose}
      title={<span className={styles.filePath}>{selection.filePath}</span>}
      badge={<span className={styles.lineRange}>{lineRange}</span>}
      className={styles.codeModal}
    >
      <div className={styles.codeWrapper}>
        <SyntaxHighlighter
          style={codeTheme}
          language={selection.language}
          showLineNumbers
          startingLineNumber={selection.startLine}
          customStyle={{
            margin: 0,
            borderRadius: 0,
            fontSize: 13,
            lineHeight: 1.6,
            background: "#0a0a0f",
          }}
          lineNumberStyle={{
            minWidth: "3em",
            paddingRight: "1em",
            color: "#3a3a4e",
            userSelect: "none",
          }}
        >
          {selection.content}
        </SyntaxHighlighter>
      </div>
    </Modal>
  );
}
