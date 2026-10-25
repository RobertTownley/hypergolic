import { describe, it, expect } from "vitest";
import { formOf, inputText, outputOf, headlineOf, previewOf, firstLines, formatBytes, proseShimOf, partialCommand, splitStderr, skillActivationOf } from "./callPreview";
import type { ContentBlock } from "@/types/api";

describe("inputText", () => {
  it("renders a shell tool as its command line", () => {
    expect(inputText("cmd", { command: "grep -rn foo ." })).toBe("grep -rn foo .");
  });

  it("unwraps a shell argv recorded by older sessions", () => {
    expect(inputText("cmd", { command: ["bash", "-c", "make test"] })).toBe("make test");
    expect(inputText("cmd", { command: ["git", "status"] })).toBe("git status");
  });

  it("joins a batch of commands one per line", () => {
    expect(inputText("cmd", { commands: ["a", "b"] })).toBe("a\nb");
  });

  it("renders git as the argv the user would type", () => {
    expect(inputText("git", { operation: "log", args: ["--oneline", "-5"] })).toBe(
      "git log --oneline -5",
    );
  });

  it("renders a subagent as its prompt", () => {
    expect(inputText("research", { question: "why is it slow" })).toBe("why is it slow");
    expect(inputText("review", { context: "focus on error paths" })).toBe("focus on error paths");
  });

  it("unwraps a lone string field", () => {
    expect(inputText("open", { path: "/app/main.py" })).toBe("/app/main.py");
  });

  it("falls back to pretty JSON", () => {
    expect(inputText("thing", { a: 1, b: 2 })).toBe('{\n  "a": 1,\n  "b": 2\n}');
  });
});

describe("formOf", () => {
  it("classifies shell, subagent and plain tools", () => {
    expect(formOf("cmd")).toBe("command");
    expect(formOf("host_cmd")).toBe("command");
    expect(formOf("assign")).toBe("subagent");
    expect(formOf("review")).toBe("subagent");
    expect(formOf("git")).toBe("tool");
    expect(formOf(undefined)).toBe("tool");
  });
});

describe("proseShimOf", () => {
  it("spots a bare subagent shim invocation", () => {
    expect(proseShimOf("command", "review")).toBe("review");
    expect(proseShimOf("command", 'dispatch "check the logs"')).toBe("dispatch");
  });

  it("ignores composition, multiline scripts and non-commands", () => {
    expect(proseShimOf("command", "review | head")).toBeNull();
    expect(proseShimOf("command", "git add -A && review")).toBeNull();
    expect(proseShimOf("command", "review\necho done")).toBeNull();
    expect(proseShimOf("command", "reviewer --help")).toBeNull();
    expect(proseShimOf("command", "review-old.sh")).toBeNull();
    expect(proseShimOf("tool", "review")).toBeNull();
  });
});

describe("skillActivationOf", () => {
  it("reads the skill from the shim or the tool", () => {
    expect(skillActivationOf("cmd", { command: "activate_skill git" })).toBe("git");
    expect(skillActivationOf("cmd", { command: "activate_skill 'harness_engineering'" })).toBe("harness-engineering");
    expect(skillActivationOf("activate_skill", { name: "Git" })).toBe("git");
  });

  it("ignores composition and other commands", () => {
    expect(skillActivationOf("cmd", { command: "activate_skill git && ls" })).toBeNull();
    expect(skillActivationOf("cmd", { command: "activate_skill git\nls" })).toBeNull();
    expect(skillActivationOf("cmd", { command: "list_skills" })).toBeNull();
    expect(skillActivationOf("review", { task: "activate_skill git" })).toBeNull();
  });
});

describe("outputOf", () => {
  const block: ContentBlock = {
    type: "tool_result",
    content: [
      { type: "text", text: "one\ntwo\n\n" },
      { type: "image", source: { type: "base64", media_type: "image/png", data: "x" } },
    ],
  };

  it("splits text from images and measures the text", () => {
    const out = outputOf(block);
    expect(out.text).toBe("one\ntwo");
    expect(out.lines).toBe(2);
    expect(out.images).toHaveLength(1);
  });

  it("caches by block identity so a huge result is scanned once", () => {
    expect(outputOf(block)).toBe(outputOf(block));
  });

  it("treats a missing block as empty", () => {
    expect(outputOf(undefined).lines).toBe(0);
  });

  it("lifts a failed command's stderr out of the result", () => {
    const failed: ContentBlock = {
      type: "tool_result",
      is_error: true,
      content: [{ type: "text", text: "partial\n[stderr]\nboom: no such file\n[exit 1]\n" }],
    };
    expect(outputOf(failed).stderr).toBe("boom: no such file");
    expect(outputOf(block).stderr).toBeUndefined();
  });
});

describe("splitStderr", () => {
  it("splits stdout from the stderr tail and drops the exit marker", () => {
    expect(splitStderr("out\nmore\n\n[stderr]\nboom\nline2\n\n[exit 2]")).toEqual({
      stdout: "out\nmore",
      stderr: "boom\nline2",
    });
  });

  it("handles a result that is only stderr", () => {
    expect(splitStderr("[stderr]\nboom\n[exit 1]")).toEqual({ stdout: "", stderr: "boom" });
  });

  it("takes the last marker so a nested tool's echo stays in stdout", () => {
    expect(splitStderr("[stderr]\ninner\n[exit 1]\n[stderr]\nouter\n[exit 1]")).toEqual({
      stdout: "[stderr]\ninner\n[exit 1]",
      stderr: "outer",
    });
  });

  it("leaves plain output and a mid-line mention alone", () => {
    expect(splitStderr("out\n[exit 1]")).toEqual({ stdout: "out\n[exit 1]" });
    expect(splitStderr("see [stderr]\nfor details")).toEqual({ stdout: "see [stderr]\nfor details" });
  });

  it("reports an empty stderr block as none", () => {
    expect(splitStderr("[stderr]\n\n[exit 1]").stderr).toBeUndefined();
  });
});

describe("previews", () => {
  it("takes the first non-empty line as the headline", () => {
    expect(headlineOf("\n\ncd /app && ls\nmore")).toBe("cd /app && ls");
  });

  it("truncates an absurd single line", () => {
    expect(headlineOf("x".repeat(500))).toHaveLength(401);
  });

  it("previews the first lines of a multi-line invocation", () => {
    expect(previewOf("\ncat > f <<EOF\na\nb\n")).toBe("cat > f <<EOF\na\nb");
    expect(previewOf("1\n2\n3\n4\n5")).toBe("1\n2\n3\n4…");
    expect(previewOf("x".repeat(2000))).toHaveLength(1201);
  });

  it("clips to a line budget, head first", () => {
    expect(firstLines("1\n2\n3\n4", 2)).toBe("1\n2");
    expect(firstLines("1\n2", 5)).toBe("1\n2");
  });

  it("formats sizes", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(3 * 1024 * 1024)).toBe("3.0 MB");
  });
});

describe("partialCommand", () => {
  it("decodes the command prefix of a JSON document still streaming", () => {
    expect(partialCommand('{"container": "dev", "command": "cat <<EOF\\n# Ti')).toBe("cat <<EOF\n# Ti");
  });

  it("stops at the closing quote and decodes escapes", () => {
    expect(partialCommand('{"command": "echo \\"hi\\" \\u00e9", "container": "dev"}')).toBe('echo "hi" é');
  });

  it("drops an escape cut in half by the stream", () => {
    expect(partialCommand('{"command": "a\\')).toBe("a");
    expect(partialCommand('{"command": "a\\u00')).toBe("a");
  });

  it("is empty until the command key arrives, and ignores a commands list", () => {
    expect(partialCommand('{"container": "de')).toBe("");
    expect(partialCommand('{"commands": ["ls"]')).toBe("");
  });

  it("decodes no more than the limit", () => {
    expect(partialCommand(`{"command": "${"x".repeat(50)}`, 10)).toHaveLength(10);
  });
});
