export interface SlashCommand {
  name: string;
  argHint?: string;
  description: string;
}

const SLASH_COMMANDS: SlashCommand[] = [
  {
    name: "fork",
    argHint: "<message>",
    description: "Copy this conversation into a new session and continue there",
  },
  {
    name: "fork-with-workspace",
    argHint: "<message>",
    description: "Fork the conversation and branch off this session's committed work",
  },
  {
    name: "workflow",
    argHint: "<name>",
    description: "Start a workflow with your next message",
  },
];

/**
 * The partial command name being typed, or null when the slash menu should be
 * closed. The menu is only open while the draft is a lone `/word` — once a
 * space or newline appears the user is writing arguments (or prose).
 */
export function slashMenuQuery(text: string): string | null {
  const m = /^\/([a-zA-Z-]*)$/.exec(text);
  return m ? m[1].toLowerCase() : null;
}

/**
 * The partial workflow name being typed after `/workflow `, or null when the
 * draft is not selecting a workflow.
 */
export function workflowMenuQuery(text: string): string | null {
  const m = /^\/workflow[^\S\n]+([^\n]*)$/.exec(text);
  return m ? m[1].toLowerCase() : null;
}

export function matchSlashCommands(query: string): SlashCommand[] {
  return SLASH_COMMANDS.filter((c) => c.name.startsWith(query));
}

/**
 * Parse a submitted draft into a registered command + its argument string.
 * Returns null for plain text and for unknown `/things` (e.g. file paths),
 * which are sent as ordinary messages.
 */
export function parseSlashCommand(
  text: string,
): { command: SlashCommand; args: string } | null {
  const m = /^\/(\S+)([\s\S]*)$/.exec(text.trim());
  if (!m) return null;
  const command = SLASH_COMMANDS.find((c) => c.name === m[1].toLowerCase());
  if (!command) return null;
  return { command, args: m[2].trim() };
}
