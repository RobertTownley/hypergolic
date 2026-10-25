import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { Provider } from "react-redux";
import { MarkdownContent } from "./MarkdownContent";
import { createTestStore } from "@/test/fixtures";

function renderMarkdown(text: string, activeSessionId: string | null = "sess-1") {
  const store = createTestStore({
    sessions: {
      entities: {},
      ids: [],
      activeSessionId,
      initialized: false,
      loading: false,
      error: null,
      contextBySessionId: {},
      concludeErrorBySessionId: {},
    },
  });
  return render(
    <Provider store={store}>
      <MarkdownContent text={text} />
    </Provider>
  );
}

describe("MarkdownContent links", () => {
  it("rewrites file:// links to the raw resolve endpoint in a new tab", () => {
    const { container } = renderMarkdown("[napkin](file:///Users/me/wt/docs/n.html)");
    const a = container.querySelector("a")!;
    expect(a.getAttribute("href")).toBe(
      "/api/files/raw/resolve?session_id=sess-1&path=%2FUsers%2Fme%2Fwt%2Fdocs%2Fn.html"
    );
    expect(a.getAttribute("target")).toBe("_blank");
  });

  it("handles single-slash file: hrefs", () => {
    const { container } = renderMarkdown("[n](file:/tmp/x.html)");
    const a = container.querySelector("a")!;
    expect(a.getAttribute("href")).toBe(
      "/api/files/raw/resolve?session_id=sess-1&path=%2Ftmp%2Fx.html"
    );
  });

  it("opens external http(s) links in a new tab", () => {
    const { container } = renderMarkdown("[gh](https://github.com)");
    const a = container.querySelector("a")!;
    expect(a.getAttribute("href")).toBe("https://github.com");
    expect(a.getAttribute("target")).toBe("_blank");
    expect(a.getAttribute("rel")).toContain("noopener");
  });

  it("leaves relative links untouched", () => {
    const { container } = renderMarkdown("[doc](docs/readme.md)");
    const a = container.querySelector("a")!;
    expect(a.getAttribute("href")).toBe("docs/readme.md");
    expect(a.getAttribute("target")).toBeNull();
  });

  it("renders file:// links without href when no active session", () => {
    const { container } = renderMarkdown("[n](file:///tmp/x.html)", null);
    const a = container.querySelector("a")!;
    expect(a.getAttribute("href")).toBeNull();
  });
});
