export interface DiffRow {
  type: "context" | "add" | "del" | "hunk" | "file-header";
  oldNum: number | null;
  newNum: number | null;
  content: string;
}

export function parseDiff(patch: string, { fileHeaders = false } = {}): DiffRow[] {
  const rows: DiffRow[] = [];
  let oldLine = 0;
  let newLine = 0;

  const lines = patch.split("\n");
  if (lines[lines.length - 1] === "") lines.pop();
  for (const line of lines) {
    if (line.startsWith("diff ") && fileHeaders) {
      const m = line.match(/diff --git a\/.+ b\/(.+)/);
      rows.push({ type: "file-header", oldNum: null, newNum: null, content: m?.[1] ?? line });
      continue;
    }
    if (
      line.startsWith("diff ") ||
      line.startsWith("index ") ||
      line.startsWith("--- ") ||
      line.startsWith("+++ ") ||
      line.startsWith("old mode") ||
      line.startsWith("new mode") ||
      line.startsWith("similarity index") ||
      line.startsWith("rename from") ||
      line.startsWith("rename to") ||
      line.startsWith("new file mode") ||
      line.startsWith("deleted file mode") ||
      line.startsWith("\\")
    ) {
      continue;
    }
    if (line.startsWith("@@")) {
      const m = line.match(/@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
      if (m) {
        oldLine = parseInt(m[1], 10);
        newLine = parseInt(m[2], 10);
      }
      rows.push({ type: "hunk", oldNum: null, newNum: null, content: line });
    } else if (line.startsWith("+")) {
      rows.push({ type: "add", oldNum: null, newNum: newLine++, content: line.slice(1) });
    } else if (line.startsWith("-")) {
      rows.push({ type: "del", oldNum: oldLine++, newNum: null, content: line.slice(1) });
    } else if (line.startsWith(" ") || line === "") {
      rows.push({ type: "context", oldNum: oldLine++, newNum: newLine++, content: line.slice(1) });
    } else {
      rows.push({ type: "context", oldNum: null, newNum: null, content: line });
    }
  }
  return rows;
}

export interface SplitRow {
  hunk: DiffRow | null;
  left: DiffRow | null;
  right: DiffRow | null;
}

export function toSplitRows(rows: DiffRow[]): SplitRow[] {
  const out: SplitRow[] = [];
  let i = 0;
  while (i < rows.length) {
    const row = rows[i];
    if (row.type === "hunk" || row.type === "file-header") {
      out.push({ hunk: row, left: null, right: null });
      i++;
    } else if (row.type === "context") {
      out.push({ hunk: null, left: row, right: row });
      i++;
    } else {
      const dels: DiffRow[] = [];
      const adds: DiffRow[] = [];
      while (i < rows.length && rows[i].type === "del") dels.push(rows[i++]);
      while (i < rows.length && rows[i].type === "add") adds.push(rows[i++]);
      const n = Math.max(dels.length, adds.length);
      for (let k = 0; k < n; k++) {
        out.push({ hunk: null, left: dels[k] ?? null, right: adds[k] ?? null });
      }
    }
  }
  return out;
}
