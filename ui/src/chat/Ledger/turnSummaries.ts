import type { ContentBlock } from "@/types/api";
import type { LedgerItem } from "./ledgerModel";

type SummaryItem = Extract<LedgerItem, { kind: "summary" }>;

function isCompacted(item: LedgerItem): boolean {
  if (item.kind === "turn") return item.truncated;
  if (item.kind === "say") return item.message.truncated === true;
  return false;
}

function imagesOf(items: LedgerItem[]): ContentBlock[] {
  return items.flatMap((d) => (d.kind === "turn" ? d.calls.flatMap((c) => c.output.images) : []));
}

function nestInto(out: LedgerItem[], summary: SummaryItem): SummaryItem {
  const details: LedgerItem[] = [];
  while (out.length > 0 && isCompacted(out[out.length - 1])) {
    details.unshift(out.pop() as LedgerItem);
  }
  return { ...summary, details };
}

/** Nests each summary's compacted interior (the truncated run before it)
 * inside the summary item. */
export function nestCompactedRuns(items: LedgerItem[]): LedgerItem[] {
  const out: LedgerItem[] = [];
  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    if (item.kind !== "summary") {
      out.push(item);
      continue;
    }
    const summary = nestInto(out, item);
    const artifacts = imagesOf(summary.details);
    const reply = items[i + 1];
    if (artifacts.length === 0) out.push(summary);
    else if (reply?.kind === "turn") {
      out.push(summary, { ...reply, artifacts });
      i++;
    } else out.push({ ...summary, artifacts });
  }
  return out;
}
