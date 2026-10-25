import { useReducer, useEffect, useCallback } from "react";
import type { DocEntry, DocContent } from "@/api/docs";
import { fetchDocsList, fetchDocContent } from "@/api/docs";

let cachedEntries: DocEntry[] | null = null;
const contentCache = new Map<string, DocContent>();
let currentSlug = "readme";
type SlugListener = (slug: string) => void;
const slugListeners = new Set<SlugListener>();

function notifySlugChange(slug: string) {
  currentSlug = slug;
  slugListeners.forEach((fn) => fn(slug));
}

export function resetDocsCache() {
  cachedEntries = null;
  contentCache.clear();
  currentSlug = "readme";
}

type DocsState = {
  entries: DocEntry[];
  entriesLoading: boolean;
  selectedSlug: string;
  content: DocContent | null;
  contentLoading: boolean;
  error: string | null;
};

type DocsAction =
  | { type: "ENTRIES_OK"; entries: DocEntry[] }
  | { type: "ENTRIES_ERROR"; error: string }
  | { type: "SELECT_SLUG"; slug: string }
  | { type: "CONTENT_LOADING" }
  | { type: "CONTENT_OK"; content: DocContent }
  | { type: "CONTENT_ERROR"; error: string };

function docsReducer(state: DocsState, action: DocsAction): DocsState {
  switch (action.type) {
    case "ENTRIES_OK": return { ...state, entries: action.entries, entriesLoading: false };
    case "ENTRIES_ERROR": return { ...state, error: action.error, entriesLoading: false };
    case "SELECT_SLUG": return { ...state, selectedSlug: action.slug, contentLoading: !contentCache.has(action.slug), content: contentCache.get(action.slug) ?? null };
    case "CONTENT_LOADING": return { ...state, contentLoading: true };
    case "CONTENT_OK": return { ...state, content: action.content, contentLoading: false };
    case "CONTENT_ERROR": return { ...state, error: action.error, contentLoading: false };
  }
}

export function useDocs() {
  const [state, dispatch] = useReducer(docsReducer, {
    entries: cachedEntries ?? [],
    entriesLoading: cachedEntries === null,
    selectedSlug: currentSlug,
    content: contentCache.get(currentSlug) ?? null,
    contentLoading: !contentCache.has(currentSlug),
    error: null,
  });
  const { entries, entriesLoading, selectedSlug, content, contentLoading, error } = state;

  useEffect(() => {
    const listener = (slug: string) => dispatch({ type: "SELECT_SLUG", slug });
    slugListeners.add(listener);
    return () => { slugListeners.delete(listener); };
  }, []);

  useEffect(() => {
    if (cachedEntries) return;
    let cancelled = false;
    const load = async () => {
      try {
        const data = await fetchDocsList();
        if (cancelled) return;
        cachedEntries = data;
        dispatch({ type: "ENTRIES_OK", entries: data });
      } catch (err: unknown) {
        if (cancelled) return;
        dispatch({ type: "ENTRIES_ERROR", error: (err as Error).message ?? "Failed to load docs" });
      }
    };
    void load();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (contentCache.has(selectedSlug)) return;
    let cancelled = false;
    dispatch({ type: "CONTENT_LOADING" });
    const load = async () => {
      try {
        const data = await fetchDocContent(selectedSlug);
        if (cancelled) return;
        contentCache.set(selectedSlug, data);
        dispatch({ type: "CONTENT_OK", content: data });
      } catch (err: unknown) {
        if (cancelled) return;
        dispatch({ type: "CONTENT_ERROR", error: (err as Error).message ?? "Failed to load doc" });
      }
    };
    void load();
    return () => { cancelled = true; };
  }, [selectedSlug]);

  const selectDoc = useCallback((slug: string) => { notifySlugChange(slug); }, []);

  return { entries, entriesLoading, selectedSlug, content, contentLoading, error, selectDoc };
}
