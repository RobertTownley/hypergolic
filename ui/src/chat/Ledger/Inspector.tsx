import { useEffect } from "react";
import { XIcon } from "lucide-react";
import { Base64Image, Chip, IconButton } from "@/shared/components";
import { MarkdownContent } from "@/chat/MarkdownContent";
import { useLedgerContext } from "./LedgerContext";
import { formatBytes } from "./callPreview";
import { renderAnsi } from "./ansi";
import { cx } from "@/utils/cx";
import styles from "./Ledger.module.css";

/**
 * The full payload of one call, docked beside the transcript rather than
 * covering it: reading a 4000-line result shouldn't hide the conversation
 * that produced it, and the ledger keeps its scroll position while you read.
 */
export function Inspector() {
  const { inspected, closeInspector } = useLedgerContext();

  useEffect(() => {
    if (!inspected) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        closeInspector();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [inspected, closeInspector]);

  if (!inspected) return null;

  const { output, form, label, input, status, skill } = inspected;
  const prose = form === "subagent" || skill !== undefined;

  return (
    <aside className={styles.inspector} aria-label={`${label} detail`}>
      <header className={styles.inspectorHead}>
        <span className={styles.inspectorTitle}>{label}</span>
        <Chip tone={status === "error" ? "error" : status === "ok" ? "ok" : "warning"}>{status}</Chip>
        <span className={styles.spacer} />
        <IconButton icon={<XIcon />} onClick={closeInspector} tooltip="Close (esc)" />
      </header>
      <div className={styles.inspectorSections}>
        <section className={cx(styles.inspectorSection, styles.inputSection)} aria-label="input">
          <div className={styles.sectionLabel}>
            input <span className={styles.sectionMeta}>{formatBytes(input.length)}</span>
          </div>
          <div className={styles.sectionBody}>
            <pre className={styles.inspectorPre}>{input || "(none)"}</pre>
          </div>
        </section>
        <section className={cx(styles.inspectorSection, styles.outputSection)} aria-label="output">
          <div className={styles.sectionLabel}>
            output <span className={styles.sectionMeta}>{formatBytes(output.chars)}</span>
          </div>
          <div className={styles.sectionBody}>
            {output.images.map((image, i) => (
              <Base64Image key={i} block={image} alt="Tool result" className={styles.inspectorImage} />
            ))}
            {prose ? (
              <MarkdownContent text={output.text} />
            ) : (
              <pre className={styles.inspectorPre}>
                {renderAnsi(output.text) || (output.images.length ? "" : status === "pending" ? "(still running)" : "(empty)")}
              </pre>
            )}
          </div>
        </section>
      </div>
    </aside>
  );
}
