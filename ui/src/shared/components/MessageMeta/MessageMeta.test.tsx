import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MessageMeta } from "./MessageMeta";

describe("MessageMeta", () => {
  it("renders nothing when no props are provided", () => {
    const { container } = render(<MessageMeta />);
    expect(container.firstChild).toBeNull();
  });

  it("renders a single sequence number as #N", () => {
    render(<MessageMeta sequence={5} />);
    const left = screen.getByTestId("message-meta-left");
    expect(left.textContent).toBe("#5");
    expect(screen.queryByTestId("message-meta-right")).not.toBeInTheDocument();
  });

  it("renders a sequence range as #start\u2013end when endpoints differ", () => {
    render(<MessageMeta sequence={[3, 4]} />);
    const left = screen.getByTestId("message-meta-left");
    expect(left.textContent).toBe("#3\u20134");
  });

  it("renders a sequence range as #N when start equals end", () => {
    render(<MessageMeta sequence={[7, 7]} />);
    const left = screen.getByTestId("message-meta-left");
    expect(left.textContent).toBe("#7");
  });

  it("renders effective context \u2192 output alongside sequence", () => {
    render(
      <MessageMeta
        sequence={2}
        usage={{
          input_tokens: 2,
          output_tokens: 350,
          cache_creation_input_tokens: 500,
          cache_read_input_tokens: 41000,
        }}
      />,
    );
    const left = screen.getByTestId("message-meta-left");
    expect(left.textContent).toContain("#2");
    expect(left.textContent).toContain("41.5k \u2192 350 tok");
  });

  it("renders a ledger label when inputDelta is provided", () => {
    render(
      <MessageMeta
        usage={{ input_tokens: 4000, output_tokens: 80 }}
        inputDelta={2000}
      />,
    );
    expect(screen.getByTestId("message-meta-left").textContent).toBe(
      "4.0k \u2192 2.0k in, 80 out tok",
    );
  });

  it("omits tokens when usage is all zeros or null", () => {
    const { rerender } = render(
      <MessageMeta sequence={1} usage={{ input_tokens: 0, output_tokens: 0 }} />,
    );
    expect(screen.getByTestId("message-meta-left").textContent).toBe("#1");
    rerender(<MessageMeta sequence={1} usage={null} />);
    expect(screen.getByTestId("message-meta-left").textContent).toBe("#1");
  });

  it("renders timestamp on the right when provided", () => {
    render(<MessageMeta sequence={1} timestamp="3:42 PM" />);
    expect(screen.getByTestId("message-meta-right").textContent).toBe("3:42 PM");
  });
});
