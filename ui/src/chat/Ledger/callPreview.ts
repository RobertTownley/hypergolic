import type { ContentBlock } from "@/types/api";

/** Tools whose input is a shell command line, rendered as a `$` line. */
const SHELL_TOOLS = new Set(["cmd", "host_cmd"]);
/** Tools that run a nested agent and answer in prose, not output. */
const SUBAGENT_TOOLS = new Set(["research", "assign", "review"]);

export type CallForm = "command" | "subagent" | "tool";

export function formOf(tool: string | undefined): CallForm {
  if (tool && SHELL_TOOLS.has(tool)) return "command";
  if (tool && SUBAGENT_TOOLS.has(tool)) return "subagent";
  return "tool";
}

/** Subagent tools also exposed as PATH shims, invoked through a shell tool. */
const PROSE_SHIMS = /^(research|assign|review|dispatch)(?=\s|$)/;
/** Composition means the output is no longer the shim's prose. */
const SHELL_OPERATORS = /[|;&<>]/;

/**
 * The subagent shim a shell call invokes, or null. `$ review` answers in
 * prose exactly like the `review` tool, so it earns the same rendering —
 * but only for a bare invocation, not when piped or chained.
 */
export function proseShimOf(form: CallForm, input: string): string | null {
  if (form !== "command") return null;
  const line = input.trim();
  if (line.includes("\n") || SHELL_OPERATORS.test(line)) return null;
  const match = PROSE_SHIMS.exec(line);
  return match ? match[1] : null;
}

const ACTIVATE_SKILL = /^activate_skill\s+["']?([\w-]+)["']?\s*$/;

/** Skill ids are kebab-case; the agent types them snake_case as often as not. */
export function skillKey(name: string): string {
  return name.trim().toLowerCase().replace(/_/g, "-");
}

/**
 * The skill a call activates, or null. A bare `$ activate_skill <id>` and the
 * `activate_skill` tool are the same act; anything composed with other
 * commands is not, since its exit code no longer speaks for the activation.
 */
export function skillActivationOf(tool: string | undefined, input: Record<string, unknown> | undefined): string | null {
  if (!input) return null;
  if (tool === "activate_skill") return typeof input.name === "string" ? skillKey(input.name) : null;
  if (!tool || !SHELL_TOOLS.has(tool)) return null;
  const match = ACTIVATE_SKILL.exec(shellText(input).trim());
  return match ? skillKey(match[1]) : null;
}

/** Shells named as the first word of an argv, whose `-c` script is the real input. */
const SHELL_ARGV0 = new Set(["bash", "sh", "zsh"]);

/**
 * A shell tool's input as the command line a person would type. Older sessions
 * recorded `command` as an argv (`["bash", "-c", script]`) and batches as a
 * `commands` list, so all three shapes reduce to text here.
 */
function shellText(input: Record<string, unknown>): string {
  if (Array.isArray(input.commands)) return (input.commands as string[]).join("\n");

  const command = input.command;
  if (typeof command === "string") return command;
  if (Array.isArray(command)) {
    const argv = command as string[];
    if (argv.length === 3 && SHELL_ARGV0.has(argv[0]) && argv[1] === "-c") return argv[2];
    return argv.join(" ");
  }
  return JSON.stringify(input, null, 2);
}

const JSON_ESCAPES: Record<string, string> = { n: "\n", t: "\t", r: "\r", b: "\b", f: "\f" };

/**
 * The `command` string of a shell tool's input while its JSON still streams.
 * The document is incomplete, so this decodes the string prefix by hand and
 * stops at `limit` chars: the card only shows the opening lines, and a
 * full decode per token of a long heredoc would be quadratic.
 */
export function partialCommand(json: string, limit = 2000): string {
  const start = /"command"\s*:\s*"/.exec(json);
  if (!start) return "";
  let out = "";
  for (let i = start.index + start[0].length; i < json.length && out.length < limit; i++) {
    const c = json[i];
    if (c === '"') break;
    if (c !== "\\") {
      out += c;
      continue;
    }
    const escape = json[i + 1];
    if (escape === undefined) break;
    if (escape === "u") {
      const hex = json.slice(i + 2, i + 6);
      if (hex.length < 4) break;
      out += String.fromCharCode(parseInt(hex, 16));
      i += 5;
      continue;
    }
    out += JSON_ESCAPES[escape] ?? escape;
    i++;
  }
  return out;
}

/**
 * The full input as text, in the shape the tool's operator would type it:
 * a shell command line for shell tools, the prompt for subagents, argv for
 * `git`, and pretty JSON for everything else.
 */
export function inputText(tool: string | undefined, input: Record<string, unknown> | undefined): string {
  if (!input) return "";
  if (tool && SHELL_TOOLS.has(tool)) return shellText(input);
  if (tool === "git") {
    const args = Array.isArray(input.args) ? (input.args as string[]) : [];
    return ["git", input.operation, ...args].filter(Boolean).join(" ");
  }
  if (tool && SUBAGENT_TOOLS.has(tool)) {
    const prompt = input.question ?? input.task ?? input.context;
    if (typeof prompt === "string") return prompt;
  }
  const single = Object.values(input);
  if (single.length === 1 && typeof single[0] === "string" && !single[0].includes("\n")) {
    return single[0];
  }
  return JSON.stringify(input, null, 2);
}

/**
 * Result text and images, cached on the block. Content blocks keep their
 * identity across rebuilds, so a multi-megabyte result is scanned once ever
 * rather than once per render.
 */
const outputCache = new WeakMap<ContentBlock, CallOutput>();

export interface CallOutput {
  text: string;
  lines: number;
  chars: number;
  images: ContentBlock[];
  /** What a failed command wrote to stderr, lifted out of `text`. */
  stderr?: string;
}

export const EMPTY_OUTPUT: CallOutput = { text: "", lines: 0, chars: 0, images: [] };

/**
 * A failed shell call ends with `[stderr]\n…\n[exit N]` (see
 * `format_exec_output`). The stderr is the best one-glance signal that a call
 * went wrong, so it is split out for the ledger to surface on its own. The
 * last marker wins: a nested tool's own `[stderr]` echo belongs to stdout.
 */
const STDERR_MARK = "[stderr]\n";
const EXIT_TAIL = /\n\[exit -?\d+\]$/;

export function splitStderr(text: string): { stdout: string; stderr?: string } {
  // Padded so a result that is nothing but stderr matches the same way.
  const at = `\n${text}`.lastIndexOf(`\n${STDERR_MARK}`);
  if (at < 0) return { stdout: text };
  const stderr = text.slice(at + STDERR_MARK.length).replace(EXIT_TAIL, "").replace(/\s+$/, "");
  return { stdout: text.slice(0, at).replace(/\s+$/, ""), stderr: stderr || undefined };
}

export function outputOf(block: ContentBlock | undefined): CallOutput {
  if (!block) return EMPTY_OUTPUT;
  const cached = outputCache.get(block);
  if (cached) return cached;

  const blocks = block.content ?? [];
  const text = blocks
    .filter((b) => typeof b === "object" && b.type === "text")
    .map((b) => b.text ?? "")
    .join("\n")
    .replace(/\s+$/, "");
  const images = blocks.filter((b) => typeof b === "object" && b.type === "image" && !!b.source);
  const output: CallOutput = {
    text,
    lines: text ? text.split("\n").length : 0,
    chars: text.length,
    images,
    stderr: splitStderr(text).stderr,
  };
  outputCache.set(block, output);
  return output;
}

/** First non-empty line, for the collapsed headline. */
export function headlineOf(text: string): string {
  const line = text.split("\n").find((l) => l.trim()) ?? "";
  return line.length > 400 ? `${line.slice(0, 400)}…` : line;
}

/** Lines of input the expanded card shows before its CSS clamp takes over. */
const PREVIEW_LINES = 4;
const PREVIEW_CHARS = 1200;

/**
 * The opening of the invocation, from its first non-empty line, for the
 * expanded card. The card clamps it to a few visual lines; this only bounds
 * the text handed to the DOM so a long file write stays cheap.
 */
export function previewOf(text: string): string {
  const lines = text.split("\n");
  const start = lines.findIndex((l) => l.trim());
  if (start < 0) return "";
  const head = lines.slice(start, start + PREVIEW_LINES).join("\n").replace(/\s+$/, "");
  const more = lines.length > start + PREVIEW_LINES || head.length > PREVIEW_CHARS;
  return more ? `${head.slice(0, PREVIEW_CHARS)}…` : head;
}

export function firstLines(text: string, count: number): string {
  const lines = text.split("\n");
  return lines.length <= count ? text : lines.slice(0, count).join("\n");
}

export function formatBytes(chars: number): string {
  if (chars < 1024) return `${chars} B`;
  if (chars < 1024 * 1024) return `${(chars / 1024).toFixed(1)} KB`;
  return `${(chars / (1024 * 1024)).toFixed(1)} MB`;
}
