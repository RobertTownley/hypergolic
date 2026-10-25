import { describe, it, expect } from "vitest";
import { buildLedger } from "./ledgerModel";
import { nestCompactedRuns } from "./turnSummaries";
import type { ContentBlock, Message } from "@/types/api";

let seq = 0;
function msg(role: Message["role"], content: ContentBlock[], extra: Partial<Message> = {}): Message {
  seq += 1;
  return {
    id: `m${seq}`,
    session_id: "s",
    role,
    content,
    created_at: "2025-01-01T00:00:00Z",
    ...extra,
  };
}

const text = (t: string): ContentBlock => ({ type: "text", text: t });
const shot: ContentBlock = { type: "image", source: { type: "base64", media_type: "image/png", data: "AA" } };

function compactedTurn(): Message[] {
  return [
    msg("user", [text("do the thing")]),
    msg(
      "assistant",
      [{ type: "tool_call", id: "t1", name: "cmd", input: { command: "ls" } }],
      { truncated: true, stop_reason: "tool_use" },
    ),
    msg("user", [{ type: "tool_result", tool_use_id: "t1", content: [text("files")] }], {
      truncated: true,
    }),
    msg("user", [text("[Turn Summary]\n\nlisted the files")]),
    msg("assistant", [text("done")], { stop_reason: "end_turn" }),
  ];
}

describe("nestCompactedRuns", () => {
  it("nests the truncated interior inside the summary item", () => {
    const items = nestCompactedRuns(buildLedger(compactedTurn()));
    const kinds = items.map((i) => i.kind);
    expect(kinds).toEqual(["say", "summary", "turn"]);
    const summary = items[1];
    if (summary.kind !== "summary") throw new Error("expected summary");
    expect(summary.text).toBe("listed the files");
    expect(summary.details).toHaveLength(1);
    expect(summary.details[0].kind).toBe("turn");
  });

  it("leaves non-truncated neighbors alone", () => {
    const messages = [
      msg("user", [text("hi")]),
      msg("assistant", [text("hello")], { stop_reason: "end_turn" }),
      msg("user", [text("[Turn Summary]\n\nnothing hidden")]),
    ];
    const items = nestCompactedRuns(buildLedger(messages));
    const summary = items[items.length - 1];
    if (summary.kind !== "summary") throw new Error("expected summary");
    expect(summary.details).toHaveLength(0);
    expect(items.map((i) => i.kind)).toEqual(["say", "turn", "summary"]);
  });

  it("moves compacted images to the reply that closes the group", () => {
    const messages = compactedTurn();
    messages[2].content[0].content = [text("[image attached: /tmp/a.png]"), shot];
    const items = nestCompactedRuns(buildLedger(messages));
    const reply = items[2];
    if (reply.kind !== "turn") throw new Error("expected turn");
    expect(reply.artifacts).toEqual([shot]);
  });

  it("keeps compacted images on the summary when no reply follows", () => {
    const messages = compactedTurn().slice(0, 4);
    messages[2].content[0].content = [shot];
    const summary = nestCompactedRuns(buildLedger(messages))[1];
    if (summary.kind !== "summary") throw new Error("expected summary");
    expect(summary.artifacts).toEqual([shot]);
  });
});
