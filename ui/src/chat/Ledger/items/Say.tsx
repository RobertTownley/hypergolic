import { memo } from "react";
import { InfoIcon, ScissorsIcon, UserIcon } from "lucide-react";
import { MessageMeta, ScrollBox } from "@/shared/components";
import { MarkdownContent } from "@/chat/MarkdownContent";
import { ImageThumbnail, DocumentThumbnail, CodeSelectionThumbnail } from "@/chat/attachments";
import { formatTimestamp } from "@/utils/formatTimestamp";
import type { Message } from "@/types/api";
import type { SayVariant } from "../ledgerModel";
import { parseUserContent } from "../userContent";
import { outputOf } from "../callPreview";
import { cx } from "@/utils/cx";
import styles from "./items.module.css";

/** An orphaned tool result has no turn to belong to; show enough to identify it. */
const ORPHAN_LINES = 8;

const ICONS: Record<SayVariant, React.ReactNode> = {
  user: <UserIcon />,
  interrupt: <ScissorsIcon />,
  system: <InfoIcon />,
  toolResult: null,
};

/** Anything said outside an assistant turn: the user, the system, an interrupt. */
export const Say = memo(function Say({
  message,
  variant,
  sequence,
}: {
  message: Message;
  variant: SayVariant;
  sequence?: number;
}) {
  const timestamp = message.created_at ? formatTimestamp(message.created_at) : null;

  return (
    <div
      data-message-id={message.id}
      className={cx(styles.say, styles[variant], message.truncated && styles.truncated)}
    >
      <MessageMeta sequence={sequence} timestamp={timestamp} />
      {ICONS[variant] && <span className={styles.sayIcon}>{ICONS[variant]}</span>}
      <div className={styles.sayBody}>
        {variant === "toolResult" ? (
          <ScrollBox lines={ORPHAN_LINES} className={styles.monoBox}>
            <pre className={styles.pre}>{message.content.map((b) => outputOf(b).text).join("\n\n")}</pre>
          </ScrollBox>
        ) : (
          <SaidContent message={message} />
        )}
      </div>
    </div>
  );
});

function SaidContent({ message }: { message: Message }) {
  const { images, documents, codeSelections, texts } = parseUserContent(message.content);
  return (
    <>
      {(images.length > 0 || documents.length > 0 || codeSelections.length > 0) && (
        <div className={styles.attachments}>
          {images.map((block, i) => (
            <ImageThumbnail key={`img-${i}`} block={block} />
          ))}
          {documents.map((block, i) => (
            <DocumentThumbnail key={`doc-${i}`} block={block} />
          ))}
          {codeSelections.map(({ key, selection }) => (
            <CodeSelectionThumbnail key={key} selection={selection} />
          ))}
        </div>
      )}
      {texts.map(({ key, text }) => (
        <MarkdownContent key={key} text={text} />
      ))}
    </>
  );
}
