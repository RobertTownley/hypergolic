import { contextOf, type Message, type ContentBlock, type ToolResultMeta, type UsageInfo } from "@/types/api";
import { formOf, inputText, outputOf, headlineOf, previewOf, proseShimOf, skillActivationOf, type CallForm, type CallOutput } from "./callPreview";

type CallStatus = "pending" | "ok" | "error";

export type SayVariant = "user" | "system" | "interrupt" | "toolResult";

export interface LedgerCall {
  id: string;
  tool: string;
  label: string;
  form: CallForm;
  status: CallStatus;
  /** The invocation as text; `headline` is its first line, `preview` its first few. */
  input: string;
  headline: string;
  preview: string;
  output: CallOutput;
  /** Structured detail the tool attached for the UI (see ToolResult.meta). */
  meta?: ToolResultMeta;
  /** The skill id this call activates, when it is an `activate_skill`. */
  skill?: string;
  /** Pending only: the model is still streaming the input, so nothing runs yet. */
  writing?: boolean;
  /** Pending only: epoch ms the current phase (writing, then running) began. */
  startedAt?: number;
}

export type LedgerItem =
  | {
      kind: "say";
      key: string;
      message: Message;
      variant: SayVariant;
      sequence?: number;
    }
  | {
      kind: "turn";
      key: string;
      messageId: string;
      thinking: string[];
      text: string[];
      calls: LedgerCall[];
      truncated: boolean;
      isError: boolean;
      createdAt: string;
      sequence?: number | [number, number];
      usage?: UsageInfo | null;
      /** Context growth this turn caused (its tool results + any interleaved user
       * message), measured at the next assistant call. Null for the latest turn
       * (not yet known), turns without usage, or across compaction. */
      inputDelta?: number | null;
      artifacts?: ContentBlock[];
    }
  | {
      kind: "summary";
      key: string;
      text: string;
      /** The compacted interior this summary replaced. */
      details: LedgerItem[];
      artifacts?: ContentBlock[];
      sequence?: number;
    }
  | {
      kind: "transition";
      key: string;
      toolName: string;
      workflowName?: string;
      stateName?: string;
    }
  | {
      kind: "activation";
      key: string;
      skill: string;
      call: LedgerCall;
    };

const TURN_SUMMARY_PREFIX = "[Turn Summary]";

export function turnSummaryText(message: Message): string | null {
  if (message.role !== "user" || message.content.length !== 1) return null;
  const block = message.content[0];
  if (block.type !== "text" || !block.text?.startsWith(TURN_SUMMARY_PREFIX)) return null;
  return block.text.slice(TURN_SUMMARY_PREFIX.length).trim();
}

const isWorkflowTool = (name: string) =>
  name.startsWith("workflow_transition_") || name === "activate_workflow";

export function isToolResultMessage(message: Message): boolean {
  return (
    message.role === "user" &&
    message.content.length > 0 &&
    message.content[0].type === "tool_result"
  );
}

function buildCall(use: ContentBlock, result: ContentBlock | undefined, createdAt: string): LedgerCall {
  const tool = use.name ?? "tool";
  const input = inputText(tool, use.input);
  const form = formOf(tool);
  const shim = proseShimOf(form, input);
  const shown = shim ? input.trim().slice(shim.length).trim() : input;
  return {
    id: use.id ?? `${tool}-${input.slice(0, 24)}`,
    tool,
    label: shim ?? use.display_name ?? tool,
    form: shim ? "subagent" : form,
    // No result yet means in flight — or interrupted, which the old ledger
    // dropped on the floor: an unpaired tool_use rendered as nothing at all.
    status: !result ? "pending" : result.is_error ? "error" : "ok",
    input,
    headline: headlineOf(shown),
    preview: previewOf(shown),
    output: outputOf(result),
    meta: result?.meta,
    skill: skillActivationOf(tool, use.input) ?? undefined,
    // The message lands when its input is complete, which is when it runs.
    startedAt: result ? undefined : Date.parse(createdAt),
  };
}

/** A marker, not a tool call: the activated skill's name is the headline and
 * the guidance it loaded is one click away. */
const isActivation = (c: LedgerCall) => c.skill !== undefined && c.status === "ok";

const isMarker = (c: LedgerCall) => (isWorkflowTool(c.tool) && c.status === "ok") || isActivation(c);

/**
 * The workflow and target state come from the tool's `meta`. Sessions recorded
 * before that field existed only have the human-readable result text, so those
 * fall back to scraping it.
 */
function transitionOf(call: LedgerCall, key: string): LedgerItem {
  const text = call.output.text;
  return {
    kind: "transition",
    key,
    toolName: call.tool,
    stateName: call.meta?.workflow_state_name ?? text.match(/state '([^']+)'/)?.[1],
    workflowName: call.meta?.workflow_name ?? text.match(/Workflow '([^']+)'/)?.[1],
  };
}

/**
 * Messages → the items the ledger renders. A message's sequence number is its
 * 1-based position in the transcript.
 *
 * One assistant message is one turn, whether or not it called tools: thinking,
 * prose and calls are facets of the same turn rather than three competing
 * renderers. The tool_result message that answers a turn is folded into it,
 * so results never appear as free-floating bubbles.
 */
export function buildLedger(messages: Message[]): LedgerItem[] {
  const items: LedgerItem[] = [];
  // Running context+output of the last turn with usage. The growth observed at
  // turn N was produced by turn N-1 (its tool results), so each delta is
  // attributed backward to the previously rendered turn.
  let priorTokens = 0;
  let lastTurn: Extract<LedgerItem, { kind: "turn" }> | null = null;

  for (let i = 0; i < messages.length; i++) {
    const message = messages[i];
    const sequence = i + 1;

    if (message.role === "assistant") {
      const uses = message.content.filter((b) => b.type === "tool_call");
      const next = messages[i + 1];
      const answered = uses.length > 0 && next && isToolResultMessage(next);

      const results = new Map<string, ContentBlock>();
      if (answered) {
        for (const block of next.content) {
          if (block.type === "tool_result" && block.tool_use_id) results.set(block.tool_use_id, block);
        }
      }

      if (message.usage) {
        const context = contextOf(message.usage);
        const delta = context - priorTokens;
        if (lastTurn) lastTurn.inputDelta = delta >= 0 ? delta : null;
        priorTokens = context + message.usage.output_tokens;
      }

      const calls = uses.map((use) => buildCall(use, use.id ? results.get(use.id) : undefined, message.created_at));
      const thinking = message.content
        .filter((b) => b.type === "thinking" && b.thinking?.trim())
        .map((b) => b.thinking as string);
      const text = message.content
        .filter((b) => b.type === "text" && b.text?.trim())
        .map((b) => b.text as string);

      // A transition or activation that actually happened is a marker, not a
      // tool call. Denied or failed ones stay visible so the attempt is auditable.
      const markers = calls.filter(isMarker);
      const rest = calls.filter((c) => !isMarker(c));

      for (const c of markers) {
        if (isActivation(c)) items.push({ kind: "activation", key: `activation-${message.id}-${c.id}`, skill: c.skill as string, call: c });
        else items.push(transitionOf(c, `transition-${message.id}-${c.id}`));
      }

      if (rest.length > 0 || text.length > 0 || thinking.length > 0) {
        const turn: Extract<LedgerItem, { kind: "turn" }> = {
          kind: "turn",
          key: `turn-${message.id}`,
          messageId: message.id,
          thinking,
          text,
          calls: rest,
          truncated: message.truncated === true,
          isError: message.stop_reason === "error",
          createdAt: message.created_at,
          sequence: answered ? [sequence, sequence + 1] : sequence,
          usage: message.usage,
          inputDelta: null,
        };
        items.push(turn);
        // Only usage-bearing turns take part in the accounting; a usage-less
        // turn couldn't render the delta anyway.
        if (message.usage) lastTurn = turn;
      }

      if (answered) i++;
      continue;
    }

    const summaryText = turnSummaryText(message);
    if (summaryText != null) {
      items.push({ kind: "summary", key: message.id, text: summaryText, details: [], sequence });
      continue;
    }

    if (isToolResultMessage(message)) {
      // Only reachable when a result has no turn to belong to (a repaired or
      // partially loaded transcript). Rendered plainly rather than dropped.
      items.push({ kind: "say", key: message.id, message, variant: "toolResult", sequence });
      continue;
    }

    const previous = i > 0 ? messages[i - 1] : null;
    const interrupted = message.role === "user" && previous !== null && isToolResultMessage(previous);
    items.push({
      kind: "say",
      key: message.id,
      message,
      variant: message.role === "system" ? "system" : interrupted ? "interrupt" : "user",
      sequence,
    });
  }

  return items;
}
