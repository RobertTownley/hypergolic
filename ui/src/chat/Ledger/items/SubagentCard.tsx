import { memo } from "react";
import { Chip, ScrollBox } from "@/shared/components";
import { MarkdownContent } from "@/chat/MarkdownContent";
import { useInspectorSync, useLedgerContext } from "../LedgerContext";
import { formatBytes } from "../callPreview";
import type { LedgerCall } from "../ledgerModel";
import { cx } from "@/utils/cx";
import styles from "./items.module.css";

const REPORT_LINES = 14;

/**
 * A nested agent's answer. Unlike command output this is prose meant to be
 * read, so it renders as markdown in a scrollable box rather than clipped.
 */
export const SubagentCard = memo(function SubagentCard({ call }: { call: LedgerCall }) {
  const { inspect, toggleInspect, inspected } = useLedgerContext();
  const open = inspected?.id === call.id;
  const pending = call.status === "pending";
  useInspectorSync(call);

  return (
    <div className={cx(styles.card, styles.subagent, styles[call.status], open && styles.inspected)}>
      <button
        type="button"
        className={styles.head}
        aria-pressed={open}
        onClick={() => toggleInspect(call)}
      >
        <span className={styles.sigil}>◆</span>
        <Chip tone="tool">{call.label}</Chip>
        <span className={styles.headline}>{call.headline}</span>
        {pending && <span className={styles.dots}>●●●</span>}
      </button>
      {pending ? (
        <div className={styles.pendingRow}>
          working
          <span className={styles.cursor} />
        </div>
      ) : (
        <>
          <ScrollBox lines={REPORT_LINES} className={styles.section}>
            <div className={styles.markdown}>
              <MarkdownContent text={call.output.text || "(no answer)"} />
            </div>
          </ScrollBox>
          <div className={styles.foot}>
            <span>{`${call.output.lines.toLocaleString()} lines · ${formatBytes(call.output.chars)}`}</span>
            <span className={styles.footSpacer} />
            <button type="button" className={styles.linkButton} onClick={() => inspect(call)}>
              open ↗
            </button>
          </div>
        </>
      )}
    </div>
  );
});
