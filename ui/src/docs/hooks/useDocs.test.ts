// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useDocs, resetDocsCache } from "./useDocs";
import type { DocEntry, DocContent } from "@/api/docs";

const mockEntries: DocEntry[] = [
  { slug: "readme", title: "README", filename: "readme.md" },
  { slug: "changelog", title: "Changelog", filename: "changelog.md" },
];

const mockContent: DocContent = {
  slug: "readme",
  title: "README",
  content: "# Hello",
};

vi.mock("@/api/docs", () => ({
  fetchDocsList: vi.fn(() => Promise.resolve(mockEntries)),
  fetchDocContent: vi.fn(() => Promise.resolve(mockContent)),
}));

import { fetchDocsList, fetchDocContent } from "@/api/docs";

const settle = () => act(async () => {});

beforeEach(() => {
  vi.clearAllMocks();
  resetDocsCache();
});

describe("useDocs", () => {
  it("should load entries on first render", async () => {
    const { result } = renderHook(() => useDocs());

    expect(result.current.entriesLoading).toBe(true);

    await settle();
    expect(result.current.entriesLoading).toBe(false);
    expect(result.current.entries).toEqual(mockEntries);
    expect(fetchDocsList).toHaveBeenCalledTimes(1);
  });

  it("should cache entries across renders", async () => {
    const { result, unmount } = renderHook(() => useDocs());
    await settle();
    expect(result.current.entriesLoading).toBe(false);
    unmount();

    const { result: result2 } = renderHook(() => useDocs());
    expect(result2.current.entries).toEqual(mockEntries);
    expect(result2.current.entriesLoading).toBe(false);
    expect(fetchDocsList).toHaveBeenCalledTimes(1);
  });

  it("should load content for default slug", async () => {
    const { result } = renderHook(() => useDocs());
    await settle();
    expect(result.current.content).toEqual(mockContent);
    expect(fetchDocContent).toHaveBeenCalledWith("readme");
  });

  it("should select a different doc", async () => {
    const otherContent: DocContent = { slug: "changelog", title: "Changelog", content: "# Changes" };
    vi.mocked(fetchDocContent).mockResolvedValueOnce(mockContent).mockResolvedValueOnce(otherContent);

    const { result } = renderHook(() => useDocs());
    await settle();
    expect(result.current.content).toEqual(mockContent);

    act(() => result.current.selectDoc("changelog"));
    expect(result.current.selectedSlug).toBe("changelog");

    await settle();
    expect(result.current.content).toEqual(otherContent);
    expect(fetchDocContent).toHaveBeenCalledWith("changelog");
  });

  it("should cache content by slug", async () => {
    const { result } = renderHook(() => useDocs());
    await settle();
    expect(result.current.content).toEqual(mockContent);

    const otherContent: DocContent = { slug: "changelog", title: "Changelog", content: "# Changes" };
    vi.mocked(fetchDocContent).mockResolvedValueOnce(otherContent);

    act(() => result.current.selectDoc("changelog"));
    await settle();
    expect(result.current.content).toEqual(otherContent);

    act(() => result.current.selectDoc("readme"));
    expect(result.current.content).toEqual(mockContent);
    expect(fetchDocContent).toHaveBeenCalledTimes(2);
  });

  it("should handle content loading error", async () => {
    vi.mocked(fetchDocContent).mockRejectedValueOnce(new Error("not found"));

    const { result } = renderHook(() => useDocs());
    await settle();
    expect(result.current.error).toBe("not found");
  });

  it("should handle entries loading error", async () => {
    vi.mocked(fetchDocsList).mockRejectedValueOnce(new Error("network error"));

    const { result } = renderHook(() => useDocs());
    await settle();
    expect(result.current.error).toBe("network error");
    expect(result.current.entriesLoading).toBe(false);
  });
});
