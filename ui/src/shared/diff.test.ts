import { describe, it, expect } from "vitest";
import { parseDiff, toSplitRows } from "./diff";

const PATCH = `diff --git a/f.txt b/f.txt
index 111..222 100644
--- a/f.txt
+++ b/f.txt
@@ -1,4 +1,5 @@
 keep
-old line
+new line
+added line
 tail
`;

describe("parseDiff", () => {
  it("parses hunks with line numbers", () => {
    const rows = parseDiff(PATCH);
    expect(rows[0]).toMatchObject({ type: "hunk" });
    expect(rows[1]).toMatchObject({ type: "context", oldNum: 1, newNum: 1, content: "keep" });
    expect(rows[2]).toMatchObject({ type: "del", oldNum: 2, newNum: null, content: "old line" });
    expect(rows[3]).toMatchObject({ type: "add", oldNum: null, newNum: 2, content: "new line" });
    expect(rows[4]).toMatchObject({ type: "add", newNum: 3, content: "added line" });
    expect(rows[5]).toMatchObject({ type: "context", oldNum: 3, newNum: 4, content: "tail" });
  });

  it("skips file headers and rename metadata", () => {
    const rows = parseDiff(
      "diff --git a/a.txt b/b.txt\nsimilarity index 100%\nrename from a.txt\nrename to b.txt\n",
    );
    expect(rows).toEqual([]);
  });

  it("handles no-newline markers", () => {
    const rows = parseDiff("@@ -1 +1 @@\n-a\n+b\n\\ No newline at end of file\n");
    expect(rows.map((r) => r.type)).toEqual(["hunk", "del", "add"]);
  });
});

describe("toSplitRows", () => {
  it("pairs del/add runs side by side", () => {
    const split = toSplitRows(parseDiff(PATCH));
    expect(split[0].hunk).not.toBeNull();
    // context row mirrors both sides
    expect(split[1].left?.content).toBe("keep");
    expect(split[1].right?.content).toBe("keep");
    // del paired with first add
    expect(split[2].left?.content).toBe("old line");
    expect(split[2].right?.content).toBe("new line");
    // surplus add gets a blank left cell
    expect(split[3].left).toBeNull();
    expect(split[3].right?.content).toBe("added line");
  });
});
