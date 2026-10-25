import { useCallback } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { codeTheme } from "@/shared/codeTheme";
import type { LineSelection } from "@/hooks/useLineSelection";
import styles from "./FileViewer.module.css";

interface CodeViewProps {
  content: string;
  language: string;
  selection: LineSelection | null;
  onLineMouseDown: (lineNumber: number, shiftKey: boolean) => void;
  onLineMouseEnter: (lineNumber: number) => void;
  selecting: boolean;
}

export function CodeView({ content, language, selection, onLineMouseDown, onLineMouseEnter, selecting }: CodeViewProps) {
  const lineProps = useCallback(
    (lineNumber: number) => {
      const isSelected =
        selection !== null &&
        lineNumber >= Math.min(selection.start, selection.end) &&
        lineNumber <= Math.max(selection.start, selection.end);

      return {
        style: {
          background: isSelected ? "rgba(99, 102, 241, 0.15)" : undefined,
          display: "block",
          cursor: selecting ? "grabbing" : "pointer",
        } as React.CSSProperties,
        onMouseDown: (e: React.MouseEvent) => {
          e.preventDefault();
          onLineMouseDown(lineNumber, e.shiftKey);
        },
        onMouseEnter: () => {
          onLineMouseEnter(lineNumber);
        },
      };
    },
    [selection, onLineMouseDown, onLineMouseEnter, selecting],
  );

  return (
    <div className={styles.codeWrapper}>
      <SyntaxHighlighter
        style={codeTheme}
        language={language}
        showLineNumbers
        wrapLines
        lineProps={lineProps}
        customStyle={{
          margin: 0,
          borderRadius: 0,
          fontSize: 13,
          lineHeight: 1.6,
          background: "#0a0a0f",
          minHeight: "100%",
        }}
        lineNumberStyle={{
          minWidth: "3em",
          paddingRight: "1em",
          color: "#3a3a4e",
          userSelect: "none",
        }}
      >
        {content}
      </SyntaxHighlighter>
    </div>
  );
}
