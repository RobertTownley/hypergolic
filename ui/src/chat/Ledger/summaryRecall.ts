import type { ContentBlock, Message } from "@/types/api";

function innerText(blocks: ContentBlock[] | undefined): string {
  return (blocks ?? [])
    .map((b) => (b.type === "text" ? (b.text ?? "") : b.type === "image" ? "[image omitted]" : ""))
    .filter(Boolean)
    .join("\n");
}

function blockText(b: ContentBlock): string | null {
  if (b.type === "text") return b.text?.trim() ? b.text : null;
  if (b.type === "tool_call") return `[Tool call: ${b.name}(${JSON.stringify(b.input ?? {})})]`;
  if (b.type === "tool_result") {
    return `[Tool ${b.is_error ? "error" : "result"}]:\n${innerText(b.content)}`;
  }
  if (b.type === "image") return "[image omitted]";
  return null;
}

/** The raw transcript a summary replaced, flattened to attachment text. */
export function serializeCompactedRun(messages: Message[], summaryId: string): string | null {
  const idx = messages.findIndex((m) => m.id === summaryId);
  if (idx < 0) return null;
  const run: Message[] = [];
  for (let i = idx - 1; i >= 0 && messages[i].truncated; i--) run.unshift(messages[i]);
  const parts = run
    .map((m) => {
      const texts = m.content.map(blockText).filter((t): t is string => t !== null);
      return texts.length > 0 ? `[${m.role}]\n${texts.join("\n")}` : null;
    })
    .filter((t): t is string => t !== null);
  return parts.length > 0 ? parts.join("\n\n") : null;
}
