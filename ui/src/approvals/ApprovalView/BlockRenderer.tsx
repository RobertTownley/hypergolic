import type {
  ResolvedBadgeBlock,
  ResolvedBlock,
  ResolvedCodeBlock,
  ResolvedForEachBlock,
  ResolvedMarkdownBlock,
  ResolvedTextBlock,
} from "@/types/api";
import { MarkdownContent } from "@/chat/MarkdownContent";
import { Chip } from "@/shared/components";
import styles from "./ApprovalView.module.css";

const BADGE_TONES: Record<string, "neutral" | "info" | "warning" | "error"> = {
  neutral: "neutral",
  info: "info",
  warn: "warning",
  danger: "error",
};

export function BlockRenderer({ block }: { block: ResolvedBlock }) {
  switch (block.type) {
    case "code":
      return <CodeBlockView block={block} />;
    case "markdown":
      return <MarkdownBlockView block={block} />;
    case "text":
      return <TextBlockView block={block} />;
    case "badge":
      return <BadgeBlockView block={block} />;
    case "for_each":
      return <ForEachBlockView block={block} />;
  }
}

function resolveMaxHeight(h: string | number): string | undefined {
  if (typeof h === "number") return `${h}px`;
  switch (h) {
    case "half": return "50vh";
    case "third": return "33vh";
    case "auto": return undefined;
    default: return undefined;
  }
}

function CodeBlockView({ block }: { block: ResolvedCodeBlock }) {
  const fenced = `\`\`\`${block.language ?? ""}\n${block.value}\n\`\`\``;
  const maxHeight = resolveMaxHeight(block.max_height);
  return (
    <div className={styles.codeBlock}>
      {block.label && <span className={styles.label}>{block.label}</span>}
      <div className={styles.codeScroll} style={maxHeight ? { maxHeight } : undefined}>
        <MarkdownContent text={fenced} />
      </div>
    </div>
  );
}

function MarkdownBlockView({ block }: { block: ResolvedMarkdownBlock }) {
  return (
    <div className={styles.markdownBlock}>
      {block.label && <span className={styles.label}>{block.label}</span>}
      <MarkdownContent text={block.value} />
    </div>
  );
}

function TextBlockView({ block }: { block: ResolvedTextBlock }) {
  if (!block.value) return null;
  return (
    <div className={styles.textBlock}>
      {block.label && <span className={styles.label}>{block.label}</span>}
      <p className={block.mono ? styles.textValueMono : styles.textValue}>{block.value}</p>
    </div>
  );
}

function BadgeBlockView({ block }: { block: ResolvedBadgeBlock }) {
  if (!block.value) return null;
  return (
    <div className={styles.badgeBlock}>
      {block.label && <span className={styles.label}>{block.label}</span>}
      <Chip tone={BADGE_TONES[block.tone] ?? "neutral"}>{block.value}</Chip>
    </div>
  );
}

function ForEachBlockView({ block }: { block: ResolvedForEachBlock }) {
  if (block.items.length === 0) {
    if (!block.empty_text) return null;
    return (
      <div className={styles.forEachEmpty}>
        {block.label && <span className={styles.label}>{block.label}</span>}
        <p className={styles.emptyText}>{block.empty_text}</p>
      </div>
    );
  }
  const separatorClass =
    block.separator === "divider" ? styles.itemDivider :
    block.separator === "gap" ? styles.itemGap : "";
  return (
    <div className={styles.forEach}>
      {block.label && <span className={styles.label}>{block.label}</span>}
      {block.items.map((item, i) => (
        <div key={i} className={`${styles.forEachItem} ${i > 0 ? separatorClass : ""}`}>
          {item.heading && <h4 className={styles.itemHeading}>{item.heading}</h4>}
          {item.blocks.map((b, j) => (
            <BlockRenderer key={j} block={b} />
          ))}
        </div>
      ))}
    </div>
  );
}
