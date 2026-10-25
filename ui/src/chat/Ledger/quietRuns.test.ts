import { describe, it, expect } from "vitest";
import { buildLedger } from "./ledgerModel";
import { foldQuietRuns } from "./quietRuns";
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

const call = (id: string): ContentBlock => ({ type: "tool_call", id, name: "cmd", input: { command: "ls" } });
const result = (id: string, blocks?: ContentBlock[]): ContentBlock => ({
  type: "tool_result",
  tool_use_id: id,
  content: blocks ?? [{ type: "text", text: "ok" }],
});
const image: ContentBlock = {
  type: "image",
  source: { type: "base64", media_type: "image/png", data: "AAAA" },
};

/** N quiet turns: thinking + an answered call, no prose. */
function quietPair(id: string): Message[] {
  return [
    msg("assistant", [{ type: "thinking", thinking: "hmm" }, call(id)], {
      usage: { input_tokens: 100, output_tokens: 50 },
    }),
    msg("user", [result(id)]),
  ];
}

const prose = () => msg("assistant", [{ type: "text", text: "done" }]);

describe("foldQuietRuns", () => {
  it("folds a quiet run before content, keeping the trailing run visible", () => {
    const items = foldQuietRuns(
      buildLedger([...quietPair("t1"), ...quietPair("t2"), prose(), ...quietPair("t3"), ...quietPair("t4")]),
    );
    expect(items.map((i) => i.kind)).toEqual(["fold", "turn", "turn", "turn"]);
    const fold = items[0];
    if (fold.kind !== "fold") throw new Error("expected fold");
    expect(fold.calls).toBe(2);
    expect(fold.thinking).toBe(2);
    expect(fold.outputTokens).toBe(100);
    expect(fold.sequence).toEqual([1, 4]);
  });

  it("leaves a single quiet turn alone", () => {
    const items = foldQuietRuns(buildLedger([...quietPair("t1"), prose()]));
    expect(items.map((i) => i.kind)).toEqual(["turn", "turn"]);
  });

  it("treats image output as content", () => {
    const withImage = [
      msg("assistant", [call("t1")]),
      msg("user", [result("t1", [image])]),
    ];
    const items = foldQuietRuns(
      buildLedger([...quietPair("t2"), ...withImage, ...quietPair("t3"), prose()]),
    );
    // The image turn breaks the run; neither side reaches MIN_RUN.
    expect(items.map((i) => i.kind)).toEqual(["turn", "turn", "turn", "turn"]);
  });

  it("keeps interrupted (pending) calls visible", () => {
    const interrupted = msg("assistant", [call("t9")]);
    const items = foldQuietRuns(
      buildLedger([...quietPair("t1"), interrupted, msg("user", [{ type: "text", text: "stop" }]), prose()]),
    );
    expect(items.some((i) => i.kind === "fold")).toBe(false);
  });

  it("holds the live turn's runs open until the session goes idle", () => {
    const earlier = [...quietPair("t1"), ...quietPair("t2"), prose()];
    const ask = msg("user", [{ type: "text", text: "next" }]);
    const current = [...quietPair("t3"), ...quietPair("t4"), prose()];
    const messages = buildLedger([...earlier, ask, ...current]);

    const live = foldQuietRuns(messages, true);
    // Earlier turns stay folded; the current turn's run does not fold mid-turn.
    expect(live.map((i) => i.kind)).toEqual(["fold", "turn", "say", "turn", "turn", "turn"]);

    const idle = foldQuietRuns(messages);
    expect(idle.map((i) => i.kind)).toEqual(["fold", "turn", "say", "fold", "turn"]);
  });

  it("sums context growth across the run", () => {
    const turn2 = [
      msg("assistant", [call("t2")], { usage: { input_tokens: 300, output_tokens: 50 } }),
      msg("user", [result("t2")]),
    ];
    const items = foldQuietRuns(buildLedger([...quietPair("t1"), ...turn2, prose()]));
    const fold = items[0];
    if (fold.kind !== "fold") throw new Error("expected fold");
    // Turn 1's growth is measured at turn 2: 300 - (100 + 50). Turn 2's is
    // unmeasured (prose has no usage), so it contributes nothing.
    expect(fold.contextGrowth).toBe(150);
  });
});
