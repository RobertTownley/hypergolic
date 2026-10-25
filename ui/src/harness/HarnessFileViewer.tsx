import { Text } from "@/shared/components/Text";
import { FileIcon, WrenchIcon } from "lucide-react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { codeTheme } from "@/shared/codeTheme";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { EmptyState } from "@/shared/components/EmptyState";
import { Spinner } from "@/shared/components/Spinner";
import { useHarness } from "./useHarness";
import styles from "@/files/FileViewer/FileViewer.module.css";

export function HarnessFileViewer() {
  const { selectedPath, fileContent, fileLoading, fileError } = useHarness();

  if (!selectedPath) {
    return (
      <EmptyState
        icon={<WrenchIcon />}
        text="Select a file to view"
        className={styles.emptyState}
      >
        <span className={styles.emptyHint}>Browse your ~/.hypergolic config</span>
      </EmptyState>
    );
  }

  if (fileLoading) {
    return <div className={styles.loadingState}><Spinner /></div>;
  }

  if (fileError) {
    return (
      <div className={styles.errorState}>
        <Text type="danger">{fileError}</Text>
      </div>
    );
  }

  if (!fileContent) return null;

  const filename = fileContent.path.split("/").pop() ?? fileContent.path;
  const isMarkdown = fileContent.language === "markdown";

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <FileIcon className={styles.headerIcon} />
        <Text className={styles.headerPath} ellipsis title={fileContent.path}>
          ~/.hypergolic/{fileContent.path}
        </Text>
        <Text className={styles.headerFilename}>{filename}</Text>
      </div>
      <div className={styles.contentArea}>
        {isMarkdown ? (
          <div className={styles.markdownContainer}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{fileContent.content}</ReactMarkdown>
          </div>
        ) : (
          <div className={styles.codeWrapper}>
            <SyntaxHighlighter
              style={codeTheme}
              language={fileContent.language}
              showLineNumbers
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
              {fileContent.content}
            </SyntaxHighlighter>
          </div>
        )}
      </div>
    </div>
  );
}
