import { describe, it, expect } from "vitest";
import { mergeSummary } from "./MergeCandidateBar";

const base = { parents: ["p1", "p2"], merged_from: "main", view: "merge" as const };

describe("mergeSummary", () => {
  it("names a clean merge explicitly", () => {
    expect(mergeSummary({ ...base, merged_count: 1, conflict_paths: [] })).toBe(
      "Clean merge of 1 commit from main; no conflict resolutions",
    );
  });

  it("counts resolved files", () => {
    expect(mergeSummary({ ...base, merged_count: 3, conflict_paths: ["a", "b"] })).toBe(
      "Merge of 3 commits from main; conflicts resolved in 2 files",
    );
  });
});
