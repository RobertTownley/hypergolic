import { useState } from "react";
import { LightbulbIcon } from "lucide-react";
import { Chip, ScrollBox } from "@/shared/components";
import { MarkdownContent, ThrottledMarkdown } from "@/chat/MarkdownContent";
import { cx } from "@/utils/cx";
import styles from "./items.module.css";

const OPEN_LINES = 28;
const LEAD_CHARS = 200;

const flatten = (text: string) => text.trim().replace(/\s+/g, " ");

/** The opening sentence, standing in for the whole block on one line. */
function lead(text: string): string {
  const flat = flatten(text);
  const sentence = new RegExp(`^.{0,${LEAD_CHARS}}?[.!?](?=\\s|$)`).exec(flat)?.[0];
  return sentence ?? (flat.length > LEAD_CHARS ? `${flat.slice(0, LEAD_CHARS)}…` : flat);
}

/**
 * The latest finished sentence of a block still streaming. It changes once per
 * sentence, not per token, so the line reads as a calm ticker, not a blur.
 */
export function latest(text: string): string {
  const flat = flatten(text);
  const done = flat.match(/[^.!?]*[.!?](?=\s|$)/g);
  const sentence = done?.[done.length - 1]?.trim();
  if (!sentence) return "";
  return sentence.length > LEAD_CHARS ? `${sentence.slice(0, LEAD_CHARS)}…` : sentence;
}

interface ThinkProps {
  text: string;
  /**
   * Deltas still arriving. Live reasoning stays one line — the latest sentence —
   * so a block that starts, grows and ends never changes the page height.
   */
  live?: boolean;
}

export function Think({ text, live = false }: ThinkProps) {
  const [open, setOpen] = useState(false);

  if (live && !open) {
    return (
      <button type="button" className={styles.thinkLine} onClick={() => setOpen(true)}>
        <LightbulbIcon className={styles.thinkIcon} />
        <span className={styles.thinkLead}>{latest(text) || "thinking"}</span>
        <span className={styles.dots}>●●●</span>
      </button>
    );
  }

  if (!open) {
    return (
      <button type="button" className={styles.thinkLine} onClick={() => setOpen(true)}>
        <LightbulbIcon className={styles.thinkIcon} />
        <span className={styles.thinkLead}>{lead(text)}</span>
        <Chip>{`${text.length.toLocaleString()} chars`}</Chip>
      </button>
    );
  }

  return (
    <div className={styles.think}>
      <button type="button" className={styles.thinkHead} onClick={() => setOpen(false)}>
        <LightbulbIcon className={styles.thinkIcon} />
        <span>thinking</span>
      </button>
      <ScrollBox lines={OPEN_LINES} className={cx(styles.thinkBody, styles.plain)}>
        {live ? <ThrottledMarkdown text={text} /> : <MarkdownContent text={text} />}
      </ScrollBox>
    </div>
  );
}
