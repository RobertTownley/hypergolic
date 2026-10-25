import type { LedgerItem } from "./ledgerModel";

type TurnItem = Extract<LedgerItem, { kind: "turn" }>;

/** A run of quiet turns folded into one expandable note. */
export interface FoldItem {
  kind: "fold";
  key: string;
  turns: TurnItem[];
  calls: number;
  thinking: number;
  outputTokens: number;
  /** Summed context growth across the run; null when no turn measured one. */
  contextGrowth: number | null;
  sequence?: [number, number];
}

export type ViewItem = LedgerItem | FoldItem;

/** Below this a run isn't worth a note — folded turns are already one row each. */
const MIN_RUN = 2;

/**
 * Quiet: nothing a reader would want inline. Prose and image output are
 * content; errors and interrupted (still-"pending") calls are worth seeing.
 */
function isQuietTurn(item: LedgerItem): item is TurnItem {
  return (
    item.kind === "turn" &&
    item.text.length === 0 &&
    !item.isError &&
    !item.artifacts?.length &&
    item.calls.every((c) => c.status !== "pending" && c.output.images.length === 0)
  );
}

function seqOf(sequence: TurnItem["sequence"]): [number, number] | null {
  if (sequence === undefined) return null;
  return Array.isArray(sequence) ? sequence : [sequence, sequence];
}

function foldOf(turns: TurnItem[]): FoldItem {
  const deltas = turns.map((t) => t.inputDelta).filter((d): d is number => d != null);
  const first = seqOf(turns[0].sequence);
  const last = seqOf(turns[turns.length - 1].sequence);
  return {
    kind: "fold",
    key: `fold-${turns[0].key}`,
    turns,
    calls: turns.reduce((n, t) => n + t.calls.length, 0),
    thinking: turns.reduce((n, t) => n + t.thinking.length, 0),
    outputTokens: turns.reduce((n, t) => n + (t.usage?.output_tokens ?? 0), 0),
    contextGrowth: deltas.length ? deltas.reduce((a, b) => a + b, 0) : null,
    sequence: first && last ? [first[0], last[1]] : undefined,
  };
}

const isUserSay = (item: LedgerItem) =>
  item.kind === "say" && (item.variant === "user" || item.variant === "interrupt");

/**
 * Collapses each maximal run of quiet turns into a fold note — except the
 * trailing run, which is the work in progress since the agent (or user) last
 * said anything and stays visible.
 *
 * While `live`, nothing after the latest user message folds either: a run
 * that folds when the agent writes a line of prose mid-turn moves the page
 * above the reader. The turn's runs fold once, when the session goes idle.
 */
export function foldQuietRuns(items: LedgerItem[], live = false): ViewItem[] {
  let end = items.length;
  while (end > 0 && isQuietTurn(items[end - 1])) end--;
  if (live) end = Math.min(end, items.findLastIndex(isUserSay) + 1);

  const out: ViewItem[] = [];
  let run: TurnItem[] = [];
  const flush = () => {
    if (run.length >= MIN_RUN) out.push(foldOf(run));
    else out.push(...run);
    run = [];
  };
  for (let i = 0; i < end; i++) {
    const item = items[i];
    if (isQuietTurn(item)) run.push(item);
    else {
      flush();
      out.push(item);
    }
  }
  flush();
  out.push(...items.slice(end));
  return out;
}
