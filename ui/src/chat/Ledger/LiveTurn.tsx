import { memo } from "react";
import type { StreamingBlock } from "@/store/messagesSlice";
import { Think } from "./items/Think";
import { Call } from "./items/Turn";
import { ThrottledMarkdown } from "@/chat/MarkdownContent";
import type { LedgerCall } from "./ledgerModel";
import { formOf, partialCommand, headlineOf, previewOf, EMPTY_OUTPUT } from "./callPreview";
import items from "./items/items.module.css";

/** A call announced by the stream: named, but its input is still arriving. */
function liveCall(block: StreamingBlock, index: number): LedgerCall {
  const label = block.display_name ?? block.name ?? "tool";
  const form = formOf(block.name);
  // Show the command as it is written; until its first chars land, the label.
  const typed = form === "command" ? partialCommand(block.partialJson ?? "") : "";
  const shown = typed.trim() ? typed : label;
  return {
    id: block.id ?? `live-${index}`,
    tool: block.name ?? "tool",
    label,
    form,
    status: "pending",
    writing: true,
    startedAt: block.startedAt,
    input: shown,
    headline: headlineOf(shown),
    preview: previewOf(shown),
    output: EMPTY_OUTPUT,
  };
}

/**
 * The turn in flight. Rendered from streaming deltas rather than messages, so
 * it re-renders per token — which is why it is its own component and why the
 * finished transcript above it is memoized away from these updates.
 */
export const LiveTurn = memo(function LiveTurn({ blocks }: { blocks: StreamingBlock[] }) {
  const last = blocks.length - 1;
  return (
    <div className={items.turn}>
      {blocks.map((block, i) => {
        if (block.type === "thinking") {
          return <Think key={i} text={block.thinking ?? ""} live={i === last} />;
        }
        if (block.type === "text") {
          return (
            <div key={i} data-agent-prose className={items.prose}>
              {block.text ? <ThrottledMarkdown text={block.text} /> : null}
              {i === last && <span className={items.cursor} />}
            </div>
          );
        }
        if (block.type === "tool_call") {
          // A row, as it will be once persisted: the stream must not show a
          // card that folds to a row the moment the message lands.
          return <Call key={i} call={liveCall(block, i)} rich={false} />;
        }
        return null;
      })}
    </div>
  );
});
