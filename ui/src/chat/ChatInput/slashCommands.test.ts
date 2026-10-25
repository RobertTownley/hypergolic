import { describe, expect, it } from "vitest";
import { matchSlashCommands, parseSlashCommand, slashMenuQuery, workflowMenuQuery } from "./slashCommands";

describe("slashMenuQuery", () => {
  it("opens on a lone slash", () => expect(slashMenuQuery("/")).toBe(""));
  it("tracks the partial name", () => expect(slashMenuQuery("/fo")).toBe("fo"));
  it("is case-insensitive", () => expect(slashMenuQuery("/FO")).toBe("fo"));
  it("closes once args start", () => expect(slashMenuQuery("/fork hi")).toBeNull());
  it("closes on plain text", () => expect(slashMenuQuery("hello")).toBeNull());
  it("closes mid-message", () => expect(slashMenuQuery("see /fork")).toBeNull());
  it("closes on paths", () => expect(slashMenuQuery("/tmp/x")).toBeNull());
});

describe("workflowMenuQuery", () => {
  it("opens after /workflow plus space", () => expect(workflowMenuQuery("/workflow ")).toBe(""));
  it("tracks names with spaces", () => expect(workflowMenuQuery("/workflow Code Rev")).toBe("code rev"));
  it("closes without the space", () => expect(workflowMenuQuery("/workflow")).toBeNull());
  it("closes on other commands", () => expect(workflowMenuQuery("/fork hi")).toBeNull());
  it("closes on newlines", () => expect(workflowMenuQuery("/workflow a\nb")).toBeNull());
  it("closes on newline before the name", () => expect(workflowMenuQuery("/workflow\nfoo")).toBeNull());
});

describe("matchSlashCommands", () => {
  it("lists everything for empty query", () => {
    expect(matchSlashCommands("").length).toBeGreaterThan(0);
  });
  it("filters by prefix", () => {
    expect(matchSlashCommands("fo").map((c) => c.name)).toEqual(["fork", "fork-with-workspace"]);
    expect(matchSlashCommands("fork-").map((c) => c.name)).toEqual(["fork-with-workspace"]);
    expect(matchSlashCommands("zzz")).toEqual([]);
  });
});

describe("parseSlashCommand", () => {
  it("parses a command with args", () => {
    const parsed = parseSlashCommand("/fork keep going");
    expect(parsed?.command.name).toBe("fork");
    expect(parsed?.args).toBe("keep going");
  });
  it("parses a bare command", () => {
    expect(parseSlashCommand("/fork")?.args).toBe("");
  });
  it("preserves multiline args", () => {
    expect(parseSlashCommand("/fork a\nb")?.args).toBe("a\nb");
  });
  it("parses hyphenated commands", () => {
    expect(parseSlashCommand("/fork-with-workspace go")?.command.name).toBe("fork-with-workspace");
  });
  it("ignores unknown commands", () => expect(parseSlashCommand("/nope hi")).toBeNull());
  it("ignores file paths", () => expect(parseSlashCommand("/tmp/x is broken")).toBeNull());
  it("ignores plain text", () => expect(parseSlashCommand("hello")).toBeNull());
});
