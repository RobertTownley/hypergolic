import { useDocs } from "@/docs/hooks/useDocs";
import type { DocContent } from "@/api/docs";

export interface DocsViewerState {
  content: DocContent | null;
  contentLoading: boolean;
  error: string | null;
  selectDoc: (slug: string) => void;
}

export function useDocsViewer(): DocsViewerState {
  const { content, contentLoading, error, selectDoc } = useDocs();
  return { content, contentLoading, error, selectDoc };
}
