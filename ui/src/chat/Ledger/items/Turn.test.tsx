import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { configureStore } from "@reduxjs/toolkit";
import { Provider } from "react-redux";
import messagesReducer from "@/store/messagesSlice";
import { LedgerProvider } from "../LedgerContext";
import { Turn } from "./Turn";
import type { LedgerCall } from "../ledgerModel";

vi.mock("@/chat/MarkdownContent", () => ({
  MarkdownContent: ({ text }: { text: string }) => <div>{text}</div>,
}));

function call(overrides: Partial<LedgerCall> = {}): LedgerCall {
  return {
    id: "t1",
    tool: "cmd",
    label: "Command",
    form: "command",
    status: "ok",
    input: "ls -la",
    headline: "ls -la",
    preview: "ls -la",
    output: { text: "file-a\nfile-b", lines: 2, chars: 13, images: [] },
    ...overrides,
  };
}

const renderTurn = (props: Partial<Parameters<typeof Turn>[0]> = {}) =>
  render(
    <Provider store={configureStore({ reducer: { messages: messagesReducer } })}>
      <LedgerProvider viewportRef={{ current: null }}>
        <Turn thinking={[]} text={["Done."]} calls={[call()]} {...props} />
      </LedgerProvider>
    </Provider>,
  );

describe("Turn", () => {
  it("shows a failed call's stderr under its folded row", () => {
    const text = "[stderr]\ncommand not found: mcp\n[exit 127]";
    renderTurn({
      calls: [call({ status: "error", output: { text, lines: 3, chars: text.length, images: [], stderr: "command not found: mcp" } })],
    });
    expect(screen.getByTestId("stderr").textContent).toContain("command not found: mcp");
    expect(screen.queryByText(/\[exit 127\]/)).toBeNull();
  });

  it("folds calls to one line each, prose intact", () => {
    renderTurn();
    expect(screen.getByText("Done.")).toBeTruthy();
    expect(screen.getByText("ls -la")).toBeTruthy();
    expect(screen.getByText("exit 0")).toBeTruthy();
    expect(screen.queryByText(/file-a/)).toBeNull();
  });

  it("expands to full cards from the turn caret", () => {
    renderTurn();
    fireEvent.click(screen.getByLabelText("Expand calls"));
    expect(screen.getByText(/file-a/)).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Fold calls"));
    expect(screen.queryByText(/file-a/)).toBeNull();
  });

  it("never folds a subagent answer", () => {
    renderTurn({
      calls: [call({ id: "s1", tool: "review", label: "review", form: "subagent", headline: "review the branch", output: { text: "Looks good.", lines: 1, chars: 11, images: [] } })],
    });
    expect(screen.getByText("Looks good.")).toBeTruthy();
    expect(screen.queryByLabelText("Expand calls")).toBeNull();
  });
});
