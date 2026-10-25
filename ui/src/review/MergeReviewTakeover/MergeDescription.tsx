import { useState } from "react";
import { MarkdownContent } from "@/chat/MarkdownContent";
import styles from "./MergeReviewTakeover.module.css";

export function MergeDescription({ text }: { text: string }) {
  const [open, setOpen] = useState(true);
  return (
    <div className={styles.commitMsgBar} aria-label="Merge description">
      <span className={styles.commitMsgLabel}>Description</span>
      <div className={`${styles.commitMsgContent} ${styles.description}`}>
        {open ? <MarkdownContent text={text} /> : (
          <span className={styles.commitMsgSubject}>{text.split("\n")[0].replace(/^#+\s*/, "")}</span>
        )}
      </div>
      <button className={styles.commitMsgToggle} onClick={() => setOpen((v) => !v)}>
        {open ? "Hide description" : "Show description"}
      </button>
    </div>
  );
}
