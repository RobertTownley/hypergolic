import { memo, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";
import { Spinner } from "@/shared/components/Spinner";
import { MarkdownCode } from "@/shared/components/MarkdownCode";
import { useDocsViewer } from "./useDocsViewer";
import styles from "./DocsViewer.module.css";

const DOC_LINK_PATTERN = /^(?:docs\/)?([\w-]+)\.md(?:#[\w-]*)?$/;

function slugFromDocPath(href: string): string | null {
  const match = DOC_LINK_PATTERN.exec(href);
  if (!match) return null;
  return match[1];
}

const DocsMarkdown = memo(function DocsMarkdown({
  text,
  onNavigate,
}: {
  text: string;
  onNavigate: (slug: string) => void;
}) {
  const components: Components = useMemo(
    () => ({
      code: MarkdownCode,
      a({ href, children, ...rest }) {
        if (href) {
          const slug = slugFromDocPath(href);
          if (slug) {
            return (
              <a
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  onNavigate(slug);
                }}
                className={styles.docLink}
                {...rest}
              >
                {children}
              </a>
            );
          }

          if (href.startsWith("http://") || href.startsWith("https://")) {
            return (
              <a href={href} target="_blank" rel="noopener noreferrer" {...rest}>
                {children}
              </a>
            );
          }
        }

        return <a href={href} {...rest}>{children}</a>;
      },
    }),
    [onNavigate],
  );

  return (
    <div className={styles.markdown}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {text}
      </ReactMarkdown>
    </div>
  );
});

export function DocsViewer() {
  const { content, contentLoading, error, selectDoc } = useDocsViewer();

  if (contentLoading) {
    return (
      <div className={styles.loading}>
        <Spinner />
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.error}>
        <span>{error}</span>
      </div>
    );
  }

  if (!content) {
    return null;
  }

  return (
    <div className={styles.container}>
      <div className={styles.content}>
        <DocsMarkdown text={content.content} onNavigate={selectDoc} />
      </div>
    </div>
  );
}
