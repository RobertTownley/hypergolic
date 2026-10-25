import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ResolvedApprovalView } from "@/types/api";
import { ApprovalView } from "./ApprovalView";

function renderBlocks(...blocks: ResolvedApprovalView["blocks"]) {
  return render(<ApprovalView view={{ blocks, show_raw_json: true }} />);
}

const code = (value: string, language: string): ResolvedApprovalView["blocks"][number] => ({
  type: "code", value, language, label: null, max_height: "third",
});

describe("ApprovalView", () => {
  it("renders nothing when blocks is empty", () => {
    const { container } = renderBlocks();
    expect(container.firstChild).toBeNull();
  });

  it("renders a code block", () => {
    const { container } = renderBlocks({
      type: "code", value: "ls -la", language: "bash", label: null, max_height: "half",
    });
    // Prism tokenizes the value into spans; match on combined text content.
    expect(container.textContent).toContain("ls");
    expect(container.textContent).toContain("-la");
  });

  it("renders a badge block with label", () => {
    renderBlocks({ type: "badge", value: "/tmp", label: "CWD", tone: "info" });
    expect(screen.getByText("CWD")).toBeInTheDocument();
    expect(screen.getByText("/tmp")).toBeInTheDocument();
  });

  it("hides a badge when value is empty", () => {
    const { container } = renderBlocks({ type: "badge", value: "", label: "CWD", tone: "info" });
    expect(container.textContent).not.toContain("CWD");
  });

  it("renders a for_each block with headings and nested code", () => {
    renderBlocks({
      type: "for_each",
      label: null,
      separator: "divider",
      empty_text: null,
      items: [
        { heading: "a.py", blocks: [code("x=1", "python")] },
        { heading: "b.ts", blocks: [code("const x=1", "typescript")] },
      ],
    });
    expect(screen.getByText("a.py")).toBeInTheDocument();
    expect(screen.getByText("b.ts")).toBeInTheDocument();
    // Code values are tokenized into spans by Prism; assert on aggregate text.
    const text = (document.body.textContent ?? "").replace(/\s+/g, "");
    expect(text).toContain("x=1");
    expect(text).toContain("constx=1");
  });

  it("renders empty_text when for_each items is empty", () => {
    renderBlocks({
      type: "for_each", label: null, separator: "divider", empty_text: "No files.", items: [],
    });
    expect(screen.getByText("No files.")).toBeInTheDocument();
  });

  it("renders a text block with mono style", () => {
    renderBlocks({ type: "text", value: "value-1", label: "Key", mono: true });
    expect(screen.getByText("value-1")).toBeInTheDocument();
    expect(screen.getByText("Key")).toBeInTheDocument();
  });
});
