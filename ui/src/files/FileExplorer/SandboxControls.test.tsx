import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SourceToggle } from "./SourceToggle";
import { SandboxSelect } from "./SandboxSelect";


describe("SourceToggle", () => {
  it("marks the active source and switches on click", () => {
    const onChange = vi.fn();
    render(<SourceToggle value="host" onChange={onChange} />);

    const sandboxTab = screen.getByRole("tab", { name: "Session Sandbox" });
    expect(screen.getByRole("tab", { name: "Host" })).toHaveAttribute("aria-selected", "true");
    expect(sandboxTab).toHaveAttribute("aria-selected", "false");

    fireEvent.click(sandboxTab);
    expect(onChange).toHaveBeenCalledWith("sandbox");
  });
});

describe("SandboxSelect", () => {
  const options = [
    { value: "worktree", label: "Project worktree" },
    { value: "shared", label: "Shared scratchpad" },
  ];

  it("shows the selected option label", () => {
    render(<SandboxSelect options={options} value="shared" onChange={() => {}} />);
    expect(screen.getByText("Shared scratchpad")).toBeInTheDocument();
  });

  it("shows the placeholder when nothing is selected", () => {
    render(<SandboxSelect options={options} value={null} onChange={() => {}} placeholder="Root" />);
    expect(screen.getByText("Root")).toBeInTheDocument();
  });

  it("opens and reports the chosen value", () => {
    const onChange = vi.fn();
    render(<SandboxSelect options={options} value="worktree" onChange={onChange} />);

    fireEvent.click(screen.getByRole("button"));
    fireEvent.click(screen.getByRole("option", { name: "Shared scratchpad" }));
    expect(onChange).toHaveBeenCalledWith("shared");
  });

  it("is disabled when there are no options", () => {
    render(<SandboxSelect options={[]} value={null} onChange={() => {}} disabled />);
    expect(screen.getByRole("button")).toBeDisabled();
  });
});
