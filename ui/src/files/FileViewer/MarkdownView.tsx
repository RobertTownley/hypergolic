import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import styles from "./FileViewer.module.css";

export function MarkdownView({ content }: { content: string }) {
  return (
    <div className={styles.markdownContainer}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}
