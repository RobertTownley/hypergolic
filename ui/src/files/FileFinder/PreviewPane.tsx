import { useEffect, useRef } from "react";
import { FileIcon } from "lucide-react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import type { FileContentResponse } from "@/types/api";
import { codeTheme } from "@/shared/codeTheme";
import styles from "./FileFinder.module.css";

export function PreviewPane({
  preview,
  loading,
  error,
  highlightLine,
}: {
  preview: FileContentResponse | null;
  loading: boolean;
  error: string | null;
  highlightLine: number | null;
}) {
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!highlightLine || !contentRef.current) return;
    requestAnimationFrame(() => {
      const lineEl = contentRef.current?.querySelector(
        `[data-line="${highlightLine}"]`,
      ) as HTMLElement | null;
      lineEl?.scrollIntoView({ block: "center" });
    });
  }, [highlightLine, preview]);

  if (error) {
    return (
      <div className={styles.previewPane}>
        <div className={styles.previewError}>{error}</div>
      </div>
    );
  }

  if (!preview && !loading) {
    return (
      <div className={styles.previewPane}>
        <div className={styles.previewEmpty}>No file selected</div>
      </div>
    );
  }

  if (loading && !preview) {
    return (
      <div className={styles.previewPane}>
        <div className={styles.previewLoading}>Loading{"\u2026"}</div>
      </div>
    );
  }

  if (!preview) return null;

  const fileName = preview.path.split("/").pop() ?? preview.path;
  const MAX_PREVIEW_BYTES = 100_000;
  const tooLarge = preview.content.length > MAX_PREVIEW_BYTES;

  return (
    <div className={styles.previewPane}>
      <div className={styles.previewHeader}>
        <FileIcon className={styles.previewHeaderIcon} />
        <span className={styles.previewHeaderPath}>{fileName}</span>
      </div>
      {tooLarge ? (
        <div className={styles.previewEmpty}>File too large to preview</div>
      ) : (
        <div className={styles.previewContent} ref={contentRef}>
          <SyntaxHighlighter
            style={codeTheme}
            language={preview.language}
            showLineNumbers
            wrapLines
            lineProps={(lineNumber: number) => ({
              style: {
                display: "block",
                background:
                  lineNumber === highlightLine
                    ? "rgba(99, 102, 241, 0.15)"
                    : undefined,
              },
              "data-line": lineNumber,
            })}
            customStyle={{
              margin: 0,
              borderRadius: 0,
              fontSize: 12,
              lineHeight: 1.5,
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
            {preview.content}
          </SyntaxHighlighter>
        </div>
      )}
    </div>
  );
}
