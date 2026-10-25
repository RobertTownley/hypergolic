import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Think } from "./Think";

vi.mock("@/chat/MarkdownContent", () => ({
  MarkdownContent: ({ text }: { text: string }) => <div data-testid="md">{text}</div>,
  ThrottledMarkdown: ({ text }: { text: string }) => <div data-testid="md-live">{text}</div>,
}));

const long = Array.from({ length: 40 }, (_, i) => `line ${i}`).join("\n");

const box = (container: HTMLElement) => container.querySelector<HTMLElement>("[style*='--sb-lines']");

describe("Think", () => {
  it("folds to its opening sentence on one line", () => {
    render(<Think text={"I need the base URLs first. Then the registry."} />);
    const line = screen.getByRole("button");
    expect(line.textContent).toContain("I need the base URLs first.");
    expect(line.textContent).not.toContain("Then the registry");
    expect(screen.queryByTestId("md")).toBeNull();
  });

  it("opens into a bounded box holding the whole reasoning", () => {
    const { container } = render(<Think text={long} />);
    fireEvent.click(screen.getByRole("button"));
    // Nothing is withheld from the DOM: the cap is a scroll height, not a slice.
    expect(screen.getByTestId("md").textContent).toBe(long);
    expect(Number(box(container)!.style.getPropertyValue("--sb-lines"))).toBeGreaterThan(6);
  });

  it("streams live as one line holding the latest finished sentence", () => {
    render(<Think text={"First I read the config. Then I check the proxy. Then the ima"} live />);
    const line = screen.getByRole("button");
    expect(line.textContent).toContain("Then I check the proxy.");
    expect(line.textContent).not.toContain("First I read");
    expect(line.textContent).not.toContain("Then the ima");
    expect(screen.queryByTestId("md-live")).toBeNull();
  });

  it("opens live reasoning into a bounded, throttled box", () => {
    const { container } = render(<Think text={long} live />);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByTestId("md-live").textContent).toBe(long);
    expect(box(container)).not.toBeNull();
  });
});
