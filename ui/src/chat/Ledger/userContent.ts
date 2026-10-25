import type { ContentBlock, CodeSelection } from "@/types/api";

export interface UserContent {
  images: ContentBlock[];
  documents: ContentBlock[];
  codeSelections: { key: string; selection: CodeSelection }[];
  texts: { key: string; text: string }[];
}

const CODE_SELECTION_RE =
  /^\[Code Selection\] File: (.+), Lines? (\d+)(?:-(\d+))?\n```(\w*)\n([\s\S]*?)\n```$/;

function parseCodeSelection(text: string): CodeSelection | null {
  const match = text.match(CODE_SELECTION_RE);
  if (!match) return null;
  return {
    filePath: match[1],
    startLine: parseInt(match[2], 10),
    endLine: match[3] ? parseInt(match[3], 10) : parseInt(match[2], 10),
    content: match[5],
    language: match[4] || "text",
  };
}

/** Splits a user message into its attachments and its prose. */
export function parseUserContent(content: ContentBlock[]): UserContent {
  const images = content.filter((b) => b.type === "image" && b.source);
  const documents = content.filter((b) => b.type === "document" && b.source);
  const codeSelections: UserContent["codeSelections"] = [];
  const texts: UserContent["texts"] = [];

  content.forEach((block, i) => {
    if (block.type !== "text" || !block.text) return;
    const selection = parseCodeSelection(block.text);
    if (selection) codeSelections.push({ key: `cs-${i}`, selection });
    else texts.push({ key: `t-${i}`, text: block.text });
  });

  return { images, documents, codeSelections, texts };
}
