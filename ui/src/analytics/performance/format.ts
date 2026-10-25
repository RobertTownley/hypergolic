const EMPTY = "—";

export function formatBytes(n: number | null): string {
  if (n === null) return EMPTY;
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let value = n;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export function formatCores(n: number | null): string {
  return n === null ? EMPTY : `${n.toFixed(2)} cores`;
}

/** Axis ticks: two significant digits, so small ranges do not repeat a label. */
export function formatAxisNumber(n: number): string {
  return n === 0 ? "0" : String(Number(n.toPrecision(2)));
}

export function formatShare(n: number | null): string {
  return n === null || Number.isNaN(n) ? EMPTY : `${Math.round(n * 100)}%`;
}

export function formatSeconds(n: number | null): string {
  if (n === null) return EMPTY;
  if (n < 1) return `${Math.round(n * 1000)} ms`;
  if (n < 120) return `${n.toFixed(1)} s`;
  if (n < 7200) return `${(n / 60).toFixed(1)} min`;
  return `${(n / 3600).toFixed(1)} h`;
}
