import { describe, it, expect } from "vitest";
import { buildLedger } from "./ledgerModel";
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

const call = (id: string, name: string, input: Record<string, unknown> = {}): ContentBlock => ({
  type: "tool_call",
  id,
  name,
  input,
});

const result = (id: string, text: string, extra: Partial<ContentBlock> = {}): ContentBlock => ({
  type: "tool_result",
  tool_use_id: id,
  content: [{ type: "text", text }],
  ...extra,
});

describe("buildLedger", () => {
  it("folds a tool result into the turn that called it", () => {
    const items = buildLedger([
      msg("assistant", [
        { type: "thinking", thinking: "hmm" },
        { type: "text", text: "running it" },
        call("t1", "cmd", { command: "ls -la" }),
      ]),
      msg("user", [result("t1", "a\nb\nc")]),
    ]);

    expect(items).toHaveLength(1);
    const turn = items[0];
    if (turn.kind !== "turn") throw new Error("expected a turn");
    expect(turn.thinking).toEqual(["hmm"]);
    expect(turn.text).toEqual(["running it"]);
    expect(turn.calls[0].headline).toBe("ls -la");
    expect(turn.calls[0].status).toBe("ok");
    expect(turn.calls[0].output.lines).toBe(3);
  });

  it("keeps an unanswered call visible as pending", () => {
    const items = buildLedger([msg("assistant", [call("t1", "cmd", { command: "sleep 60" })])]);
    if (items[0].kind !== "turn") throw new Error("expected a turn");
    expect(items[0].calls[0].status).toBe("pending");
  });

  it("marks a failed call as an error", () => {
    const items = buildLedger([
      msg("assistant", [call("t1", "cmd", { command: "false" })]),
      msg("user", [result("t1", "boom", { is_error: true })]),
    ]);
    if (items[0].kind !== "turn") throw new Error("expected a turn");
    expect(items[0].calls[0].status).toBe("error");
  });

  it("collapses a successful workflow transition into a marker", () => {
    const items = buildLedger([
      msg("assistant", [call("t1", "workflow_transition_prd", { outcome: "done" })]),
      msg("user", [
        {
          ...result("t1", "Transitioned to state 'Draft' (draft)."),
          meta: { workflow_name: "PRD", workflow_state_name: "Draft" },
        },
      ]),
    ]);

    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({
      kind: "transition",
      workflowName: "PRD",
      stateName: "Draft",
    });
  });

  it("reads the transition from result prose when meta is absent", () => {
    const items = buildLedger([
      msg("assistant", [call("t1", "workflow_transition_prd", { outcome: "done" })]),
      msg("user", [result("t1", "Workflow 'PRD' — transitioned to state 'Review' (review).")]),
    ]);
    expect(items[0]).toMatchObject({ workflowName: "PRD", stateName: "Review" });
  });

  it("collapses a successful skill activation into a marker", () => {
    const items = buildLedger([
      msg("assistant", [call("t1", "cmd", { command: "activate_skill knowledge_base" })]),
      msg("user", [result("t1", "# Knowledge base\n...")]),
    ]);
    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({ kind: "activation", skill: "knowledge-base" });
  });

  it("leaves a failed skill activation as a visible call", () => {
    const items = buildLedger([
      msg("assistant", [call("t1", "cmd", { command: "activate_skill nope" })]),
      msg("user", [result("t1", "No skill 'nope'", { is_error: true })]),
    ]);
    if (items[0].kind !== "turn") throw new Error("expected a turn");
    expect(items[0].calls[0].skill).toBe("nope");
  });

  it("leaves a denied transition as a visible call", () => {
    const items = buildLedger([
      msg("assistant", [call("t1", "workflow_transition_prd", { outcome: "done" })]),
      msg("user", [result("t1", "Denied by user", { is_error: true })]),
    ]);
    if (items[0].kind !== "turn") throw new Error("expected a turn");
    expect(items[0].calls).toHaveLength(1);
  });

  it("labels a user message after a tool result as an interrupt", () => {
    const items = buildLedger([
      msg("assistant", [call("t1", "cmd", { command: "ls" })]),
      msg("user", [result("t1", "ok")]),
      msg("user", [{ type: "text", text: "stop" }]),
    ]);
    expect(items.map((i) => i.kind)).toEqual(["turn", "say"]);
    expect(items[1]).toMatchObject({ variant: "interrupt" });
  });

  it("spans the sequence range over a turn and its results", () => {
    const messages = [
      msg("assistant", [call("t1", "cmd", { command: "ls" })]),
      msg("user", [result("t1", "ok")]),
    ];
    const items = buildLedger(messages);
    if (items[0].kind !== "turn") throw new Error("expected a turn");
    expect(items[0].sequence).toEqual([1, 2]);
  });

  it("drops an assistant message with nothing to show", () => {
    expect(buildLedger([msg("assistant", [{ type: "text", text: "   " }])])).toEqual([]);
  });

  it("attributes context growth back to the turn that caused it", () => {
    const usage = (input: number, output: number, cached = 0) => ({
      usage: { input_tokens: input, output_tokens: output, cache_read_input_tokens: cached },
    });
    const items = buildLedger([
      msg("user", [{ type: "text", text: "hi" }]),
      msg("assistant", [{ type: "text", text: "a" }], usage(2000, 400)),
      msg("user", [{ type: "text", text: "more" }]),
      msg("assistant", [{ type: "text", text: "b" }], usage(100, 90, 3900)),
    ]);
    const turns = items.filter((i) => i.kind === "turn");
    // growth seen at turn 2 (4000 - (2000 + 400) = 1600) was produced by turn 1
    expect(turns[0]).toMatchObject({ inputDelta: 1600 });
    // latest turn: growth not yet observable
    expect(turns[1]).toMatchObject({ inputDelta: null });
  });

  it("nulls the prior turn's inputDelta when context shrinks (compaction)", () => {
    const items = buildLedger([
      msg("assistant", [{ type: "text", text: "a" }], { usage: { input_tokens: 5000, output_tokens: 100 } }),
      msg("assistant", [{ type: "text", text: "b" }], { usage: { input_tokens: 1000, output_tokens: 50 } }),
    ]);
    const turns = items.filter((i) => i.kind === "turn");
    expect(turns[0]).toMatchObject({ inputDelta: null });
    expect(turns[1]).toMatchObject({ inputDelta: null });
  });
});
