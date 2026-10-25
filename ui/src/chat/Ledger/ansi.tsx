import type { CSSProperties, ReactNode } from "react";

/**
 * Renders terminal output with its SGR colours. Commands print ANSI escapes
 * (vitest, pytest, git) and a <pre> shows them as raw `␛[32m` noise. Colour and
 * weight codes become styled spans; every other escape sequence is dropped.
 */

// Indexed 0–15: the normal eight, then the bright eight. Tuned for the dark theme.
const PALETTE = [
  "var(--color-text-dim)", "var(--color-error)", "var(--color-success)", "var(--color-warning)",
  "var(--color-info)", "#c084fc", "#22d3ee", "var(--color-text)",
  "var(--color-text-tertiary)", "#fca5a5", "#6ee7b7", "#fde68a",
  "#93c5fd", "#d8b4fe", "#67e8f9", "#ffffff",
];

interface Style {
  fg?: string;
  bg?: string;
  bold?: boolean;
  dim?: boolean;
  italic?: boolean;
  underline?: boolean;
}

// CSI (ESC [ … final byte), OSC (ESC ] … BEL or ST), or a lone two-byte escape.
// eslint-disable-next-line no-control-regex
const ESCAPE = /\x1b(?:\[([0-9;:?]*)([@-~])|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])/g;

function cube(n: number): string {
  if (n < 16) return PALETTE[n];
  if (n >= 232) {
    const v = 8 + (n - 232) * 10;
    return `rgb(${v},${v},${v})`;
  }
  const i = n - 16;
  const level = (c: number) => (c === 0 ? 0 : 55 + c * 40);
  return `rgb(${level(Math.floor(i / 36))},${level(Math.floor(i / 6) % 6)},${level(i % 6)})`;
}

/** Applies one SGR parameter list to the running style. */
function apply(style: Style, params: string): Style {
  const codes = (params || "0").split(/[;:]/).map((p) => (p === "" ? 0 : Number(p)));
  const next = { ...style };
  for (let i = 0; i < codes.length; i++) {
    const c = codes[i];
    if (c === 0) Object.keys(next).forEach((k) => delete next[k as keyof Style]);
    else if (c === 1) next.bold = true;
    else if (c === 2) next.dim = true;
    else if (c === 3) next.italic = true;
    else if (c === 4) next.underline = true;
    else if (c === 22) next.bold = next.dim = false;
    else if (c === 23) next.italic = false;
    else if (c === 24) next.underline = false;
    else if (c >= 30 && c <= 37) next.fg = PALETTE[c - 30];
    else if (c >= 90 && c <= 97) next.fg = PALETTE[c - 90 + 8];
    else if (c === 39) delete next.fg;
    else if (c >= 40 && c <= 47) next.bg = PALETTE[c - 40];
    else if (c >= 100 && c <= 107) next.bg = PALETTE[c - 100 + 8];
    else if (c === 49) delete next.bg;
    else if (c === 38 || c === 48) {
      const key = c === 38 ? "fg" : "bg";
      if (codes[i + 1] === 5 && i + 2 < codes.length) {
        next[key] = cube(codes[i + 2]);
        i += 2;
      } else if (codes[i + 1] === 2 && i + 4 < codes.length) {
        next[key] = `rgb(${codes[i + 2]},${codes[i + 3]},${codes[i + 4]})`;
        i += 4;
      }
    }
  }
  return next;
}

function css(style: Style): CSSProperties | undefined {
  const out: CSSProperties = {};
  if (style.fg) out.color = style.fg;
  if (style.bg) out.backgroundColor = style.bg;
  if (style.bold) out.fontWeight = 600;
  if (style.dim) out.opacity = 0.65;
  if (style.italic) out.fontStyle = "italic";
  if (style.underline) out.textDecoration = "underline";
  return Object.keys(out).length ? out : undefined;
}

/** Output text as React nodes: plain text when it holds no escapes. */
export function renderAnsi(text: string): ReactNode {
  if (!text.includes("\x1b")) return text;
  const nodes: ReactNode[] = [];
  let style: Style = {};
  let last = 0;
  const push = (end: number) => {
    if (end <= last) return;
    const chunk = text.slice(last, end);
    const s = css(style);
    nodes.push(s ? <span key={nodes.length} style={s}>{chunk}</span> : chunk);
  };
  for (const m of text.matchAll(ESCAPE)) {
    push(m.index);
    last = m.index + m[0].length;
    if (m[2] === "m") style = apply(style, m[1]);
  }
  push(text.length);
  return nodes;
}

