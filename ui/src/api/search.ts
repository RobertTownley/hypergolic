import { getJson, jsonBody } from "@/api/http";

interface FileMatch {
  type: "file";
  path: string;
  line: number | null;
  text: string | null;
}

export interface SessionMatch {
  type: "session";
  session_id: string;
  project_id: string;
  project_name: string;
  model_tier: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  match_text: string;
  match_role: string;
  first_message: string | null;
}

type SearchMatch = FileMatch | SessionMatch;

export interface UnifiedSearchResponse {
  matches: SearchMatch[];
}

export async function unifiedSearch(
  query: string,
  mode: "files" | "contents" | "all" | "sessions",
  respectGitignore: boolean,
  includeHidden: boolean,
  projectId?: string,
): Promise<UnifiedSearchResponse> {
  return getJson("/api/search", "Search failed", jsonBody({
      query,
      mode,
      respect_gitignore: respectGitignore,
      include_hidden: includeHidden,
      max_file_results: 50,
      max_session_results: 20,
      project_id: projectId ?? null,
    }));
}
