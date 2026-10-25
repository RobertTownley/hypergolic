import { memo } from "react";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";
import { useAppSelector } from "@/store";
import { MarkdownCode } from "@/shared/components/MarkdownCode";
import styles from "./MarkdownContent.module.css";

// file: is stripped by react-markdown's default sanitizer; keep it so the
// anchor renderer can rewrite it to the raw-file endpoint.
function urlTransform(url: string): string {
  return url.startsWith("file:") ? url : defaultUrlTransform(url);
}

function MarkdownLink({ href, children, ...rest }: React.AnchorHTMLAttributes<HTMLAnchorElement>) {
  const sessionId = useAppSelector((s) => s.sessions.activeSessionId);

  if (href?.startsWith("file:")) {
    let path: string;
    try {
      path = decodeURIComponent(new URL(href).pathname);
    } catch {
      path = href.replace(/^file:\/*/, "/");
    }
    const raw = sessionId
      ? `/api/files/raw/resolve?session_id=${encodeURIComponent(sessionId)}&path=${encodeURIComponent(path)}`
      : undefined;
    return (
      <a href={raw} target="_blank" rel="noopener noreferrer" {...rest}>
        {children}
      </a>
    );
  }

  const isExternal = /^https?:\/\//.test(href ?? "");
  return (
    <a
      href={href}
      {...(isExternal ? { target: "_blank", rel: "noopener noreferrer" } : {})}
      {...rest}
    >
      {children}
    </a>
  );
}

const components: Components = {
  a: MarkdownLink,
  code: MarkdownCode,
};

export const MarkdownContent = memo(function MarkdownContent({ text }: { text: string }) {
  return (
    <div className={styles.markdown}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components} urlTransform={urlTransform}>
        {text}
      </ReactMarkdown>
    </div>
  );
});
