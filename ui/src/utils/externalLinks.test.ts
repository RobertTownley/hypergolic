// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const openExternalUrl = vi.fn<(url: string) => Promise<void>>();

vi.mock("@/api/system", () => ({
  openExternalUrl: (url: string) => openExternalUrl(url),
}));

import { installExternalLinkInterceptor } from "./externalLinks";

describe("installExternalLinkInterceptor", () => {
  let cleanup: () => void;

  beforeEach(() => {
    openExternalUrl.mockReset();
    openExternalUrl.mockResolvedValue(undefined);
    cleanup = installExternalLinkInterceptor();
  });

  afterEach(() => {
    cleanup();
    document.body.innerHTML = "";
  });

  function addAnchor(href: string | null): HTMLAnchorElement {
    const a = document.createElement("a");
    if (href !== null) a.setAttribute("href", href);
    document.body.appendChild(a);
    return a;
  }

  function clickAnchor(anchor: HTMLAnchorElement, init: MouseEventInit = {}): { defaultPrevented: boolean } {
    const event = new MouseEvent("click", {
      bubbles: true,
      cancelable: true,
      button: 0,
      ...init,
    });
    let reachedWindow: boolean | undefined;
    const blockNavigation = (e: Event) => {
      reachedWindow = e.defaultPrevented;
      e.preventDefault();
    };
    window.addEventListener("click", blockNavigation);
    anchor.dispatchEvent(event);
    window.removeEventListener("click", blockNavigation);
    return { defaultPrevented: reachedWindow ?? event.defaultPrevented };
  }

  it("intercepts clicks on external http links and routes through the system opener", () => {
    const event = clickAnchor(addAnchor("https://example.com/foo"));

    expect(event.defaultPrevented).toBe(true);
    expect(openExternalUrl).toHaveBeenCalledWith("https://example.com/foo");
  });

  it("intercepts clicks that originate on a child element inside the anchor", () => {
    const a = addAnchor("https://example.com/");
    const span = document.createElement("span");
    span.textContent = "click me";
    a.appendChild(span);

    const event = new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 });
    span.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
    expect(openExternalUrl).toHaveBeenCalledWith("https://example.com/");
  });

  it.each<[string, string | null]>([
    ["same-origin links (in-app navigation)", `${window.location.origin}/docs/foo`],
    ["anchors without an href attribute", null],
    ["hash and relative links", "#section"],
    ["non-http(s) schemes like mailto:", "mailto:test@example.com"],
  ])("leaves %s alone", (_name, href) => {
    const event = clickAnchor(addAnchor(href));

    expect(event.defaultPrevented).toBe(false);
    expect(openExternalUrl).not.toHaveBeenCalled();
  });

  it("skips non-primary button clicks", () => {
    const event = clickAnchor(addAnchor("https://example.com/"), { button: 1 });

    expect(event.defaultPrevented).toBe(false);
    expect(openExternalUrl).not.toHaveBeenCalled();
  });

  it("skips clicks whose default is already prevented", () => {
    const a = addAnchor("https://example.com/");
    const blocker = (e: Event) => e.preventDefault();
    window.addEventListener("click", blocker, true);
    try {
      const event = clickAnchor(a);
      expect(openExternalUrl).not.toHaveBeenCalled();
      expect(event.defaultPrevented).toBe(true);
    } finally {
      window.removeEventListener("click", blocker, true);
    }
  });

  it("cleanup removes the listener", () => {
    cleanup();

    clickAnchor(addAnchor("https://example.com/"));

    expect(openExternalUrl).not.toHaveBeenCalled();
    cleanup = installExternalLinkInterceptor();
  });
});
