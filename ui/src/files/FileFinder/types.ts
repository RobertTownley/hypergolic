import type { SessionMatch } from "@/api/search";

export type FinderMode = "files" | "contents" | "all" | "sessions";

export const FILE_FINDER_OPEN_EVENT = "hypergolic:file-finder-open";

export type SessionSearchMatch = SessionMatch;

export type FinderResult =
  | { type: "file"; match: { path: string; line: number | null; text: string | null } }
  | { type: "session"; match: SessionMatch };
