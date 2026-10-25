import { openExternalUrl } from "@/api/system";

const EXTERNAL_SCHEME = /^https?:\/\//i;

/**
 * Returns true if the given href points to an external http(s) URL that is
 * NOT served by our own origin (so in-app navigation still works).
 */
function isExternalHref(href: string): boolean {
  if (!EXTERNAL_SCHEME.test(href)) return false;
  try {
    const url = new URL(href, window.location.href);
    return url.origin !== window.location.origin;
  } catch {
    return false;
  }
}

/**
 * Install a global capture-phase click listener that intercepts clicks on
 * anchor elements pointing to external URLs, and routes them to the host OS
 * browser via the backend. This prevents the embedded pywebview from
 * navigating away from the Hypergolic UI.
 *
 * Returns a cleanup function that removes the listener.
 */
export function installExternalLinkInterceptor(
  target: Document = document,
): () => void {
  const handler = (event: MouseEvent) => {
    // Respect modifier keys and non-primary buttons — let the browser do its
    // thing (though in pywebview these generally behave the same anyway).
    if (event.defaultPrevented) return;
    if (event.button !== 0) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      // Still want the system browser to get these clicks.
    }

    const path = event.composedPath();
    let anchor: HTMLAnchorElement | null = null;
    for (const node of path) {
      if (node instanceof HTMLAnchorElement) {
        anchor = node;
        break;
      }
    }
    if (!anchor) return;

    const href = anchor.getAttribute("href");
    if (!href) return;
    if (!isExternalHref(href)) return;

    event.preventDefault();
    event.stopPropagation();
    void openExternalUrl(anchor.href);
  };

  target.addEventListener("click", handler, true);
  return () => target.removeEventListener("click", handler, true);
}
