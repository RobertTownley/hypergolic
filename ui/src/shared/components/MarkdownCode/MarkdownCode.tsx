import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import type { Components } from "react-markdown";
import styles from "./MarkdownCode.module.css";

const WRAP = { whiteSpace: "pre-wrap", wordBreak: "break-word", overflowWrap: "anywhere" } as const;

export const MarkdownCode: NonNullable<Components["code"]> = ({ className, children, ...rest }) => {
  const match = /language-(\w+)/.exec(className || "");
  const content = String(children).replace(/\n$/, "");
  if (!match && !content.includes("\n")) {
    return (
      <code className={styles.inlineCode} {...rest}>
        {children}
      </code>
    );
  }
  const language = match?.[1] || "text";
  return (
    <SyntaxHighlighter
      style={oneDark}
      language={language}
      PreTag="div"
      wrapLongLines
      customStyle={{ margin: 0, borderRadius: 8, fontSize: 13, lineHeight: 1.5, ...WRAP }}
      codeTagProps={{
        className: `language-${language}`,
        style: { ...oneDark['code[class*="language-"]'], ...WRAP },
      }}
    >
      {content}
    </SyntaxHighlighter>
  );
};
