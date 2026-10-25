import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { renderAnsi } from "./ansi";

const html = (text: string) => render(<pre>{renderAnsi(text)}</pre>).container.querySelector("pre")!;

describe("renderAnsi", () => {
  it("passes plain text through untouched", () => {
    expect(renderAnsi("no escapes")).toBe("no escapes");
  });

  it("colours SGR runs and drops the escapes", () => {
    const pre = html("\x1b[2m Tests \x1b[22m\x1b[1m\x1b[32m458 passed\x1b[39m\x1b[22m done");
    expect(pre.textContent).toBe(" Tests 458 passed done");
    const passed = [...pre.querySelectorAll("span")].find((s) => s.textContent === "458 passed")!;
    expect(passed.style.color).toBe("var(--color-success)");
    expect(passed.style.fontWeight).toBe("600");
  });

  it("drops non-colour sequences", () => {
    expect(html("a\x1b[2Kb\x1b]0;title\x07c").textContent).toBe("abc");
  });
});
