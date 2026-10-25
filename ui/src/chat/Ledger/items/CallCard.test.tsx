import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { configureStore } from "@reduxjs/toolkit";
import { Provider } from "react-redux";
import messagesReducer, { appendToolOutput } from "@/store/messagesSlice";
import { CallCard } from "./CallCard";
import { formatElapsed } from "./Elapsed";
import { Inspector } from "../Inspector";
import { LedgerProvider } from "../LedgerContext";
import type { LedgerCall } from "../ledgerModel";

vi.mock("@/chat/MarkdownContent", () => ({
  MarkdownContent: ({ text }: { text: string }) => <div>{text}</div>,
}));

const lines = (n: number) => Array.from({ length: n }, (_, i) => `line ${i}`).join("\n");

function call(overrides: Partial<LedgerCall> = {}): LedgerCall {
  const output = { text: lines(3), lines: 3, chars: 20, images: [], ...overrides.output };
  return {
    id: "t1",
    tool: "cmd",
    label: "Command",
    form: "command",
    status: "ok",
    input: "ls -la",
    headline: "ls -la",
    preview: "ls -la",
    ...overrides,
    output,
  };
}

const makeStore = () => configureStore({ reducer: { messages: messagesReducer } });

const renderCard = (c: LedgerCall, store = makeStore()) =>
  render(
    <Provider store={store}>
      <LedgerProvider viewportRef={{ current: null }}>
        <CallCard call={c} />
        <Inspector />
      </LedgerProvider>
    </Provider>,
  );

describe("CallCard", () => {
  it("gives a failure's stderr its own section, never clipped behind stdout", () => {
    const text = `${lines(50)}\n[stderr]\nboom: bad flag\n[exit 2]`;
    renderCard(
      call({ status: "error", output: { text, lines: 53, chars: text.length, images: [], stderr: "boom: bad flag" } }),
    );
    const stderr = screen.getByTestId("stderr");
    expect(stderr.textContent).toContain("boom: bad flag");
    // The stdout pane holds stdout only; the stderr lives in its own pane.
    const pre = document.querySelector("pre")!;
    expect(pre.textContent).not.toContain("[stderr]");
  });

  it("shows the command line and how it exited", () => {
    renderCard(call());
    expect(screen.getByText("ls -la")).toBeTruthy();
    expect(screen.getByText("exit 0")).toBeTruthy();
  });

  it("clips long output at the head and says what was left out", () => {
    renderCard(call({ output: { text: lines(400), lines: 400, chars: 4000, images: [] } }));
    const pre = document.querySelector("pre")!;
    expect(pre.textContent?.startsWith("line 0")).toBe(true);
    expect(pre.textContent).not.toContain("line 399");
    expect(screen.getByText(/of 400 lines/)).toBeTruthy();
    // Output this size is a signal to the agent, not just a display problem.
    expect(screen.getByText("bloated output")).toBeTruthy();
  });

  it("gives a failure more room before clipping", () => {
    renderCard(call({ status: "error", output: { text: lines(30), lines: 30, chars: 300, images: [] } }));
    expect(screen.getByText(/^20 of 30 lines/)).toBeTruthy();
  });

  it("reports a call still in flight instead of an empty result", () => {
    renderCard(call({ status: "pending", output: { text: "", lines: 0, chars: 0, images: [] } }));
    expect(screen.getByText("running")).toBeTruthy();
    expect(screen.getByText("waiting for output")).toBeTruthy();
  });

  it("says the model is still writing a call whose input streams", () => {
    renderCard(call({ status: "pending", writing: true, output: { text: "", lines: 0, chars: 0, images: [] } }));
    expect(screen.getByText("writing")).toBeTruthy();
    expect(screen.getByText("writing input")).toBeTruthy();
    expect(screen.queryByText("running")).toBeNull();
    expect(screen.queryByText("waiting for output")).toBeNull();
  });

  it("hands the whole payload to the inspector, which the card never shows", () => {
    renderCard(call({ output: { text: lines(400), lines: 400, chars: 4000, images: [] } }));
    expect(screen.queryByRole("complementary")).toBeNull();

    fireEvent.click(screen.getByText("open ↗"));
    const panel = screen.getByRole("complementary");
    expect(panel.textContent).toContain("line 399");

    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("complementary")).toBeNull();
  });

  it("closes the inspector when the card that opened it is clicked again", () => {
    renderCard(call());
    fireEvent.click(screen.getByText("ls -la"));
    expect(screen.getByRole("complementary")).toBeTruthy();

    fireEvent.click(screen.getAllByText("ls -la")[0]);
    expect(screen.queryByRole("complementary")).toBeNull();
  });

  it("keeps an open inspector on the call as its result lands", () => {
    const running = call({ status: "pending", output: { text: "", lines: 0, chars: 0, images: [] } });
    const { rerender } = renderCard(running);
    fireEvent.click(screen.getByText("ls -la"));
    expect(screen.getByRole("complementary").textContent).toContain("pending");

    rerender(
      <Provider store={makeStore()}>
        <LedgerProvider viewportRef={{ current: null }}>
          <CallCard call={call({ output: { text: "done", lines: 1, chars: 4, images: [] } })} />
          <Inspector />
        </LedgerProvider>
      </Provider>,
    );
    const panel = screen.getByRole("complementary");
    expect(panel.textContent).toContain("done");
    expect(panel.textContent).not.toContain("pending");
  });
});

describe("live output on a pending call", () => {
  it("shows the streamed tail instead of the waiting placeholder", () => {
    const store = makeStore();
    store.dispatch(appendToolOutput({ toolUseId: "t1", text: "Building layer 3/9..." }));
    renderCard(call({ status: "pending", output: { text: "", lines: 0, chars: 0, images: [] } }), store);
    expect(screen.getByText(/Building layer 3\/9/)).toBeInTheDocument();
    expect(screen.queryByText("waiting for output")).not.toBeInTheDocument();
  });
});

describe("elapsed timer on a pending call", () => {
  const pending = (startedAt: number) =>
    call({ status: "pending", startedAt, output: { text: "", lines: 0, chars: 0, images: [] } });
  const renderLive = (c: LedgerCall, live: boolean) =>
    render(
      <Provider store={makeStore()}>
        <LedgerProvider viewportRef={{ current: null }} live={live}>
          <CallCard call={c} />
        </LedgerProvider>
      </Provider>,
    );

  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("stays hidden for the first seconds, then counts up", () => {
    renderLive(pending(Date.now()), true);
    expect(screen.queryByText(/· \d/)).toBeNull();
    act(() => vi.advanceTimersByTime(6_000));
    expect(screen.getByText("· 6s")).toBeTruthy();
    act(() => vi.advanceTimersByTime(60_000));
    expect(screen.getByText("· 1m 06s")).toBeTruthy();
  });

  it("shows no clock on a call left pending by an interrupted turn", () => {
    renderLive(pending(Date.now() - 3_600_000), false);
    expect(screen.queryByText(/· \d/)).toBeNull();
  });
});

describe("formatElapsed", () => {
  it("reads as seconds, then minutes, then hours", () => {
    expect(formatElapsed(42_900)).toBe("42s");
    expect(formatElapsed(125_000)).toBe("2m 05s");
    expect(formatElapsed(3_723_000)).toBe("1h 02m");
  });
});
